import sqlite3
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import pytz

logger = logging.getLogger(__name__)

class DatabaseService:
    """Service for managing SQLite database operations"""
    
    def __init__(self, db_file='radiance_md.db', broadcast_event=None):
        self.db_file = db_file
        self.timezone = pytz.timezone('US/Eastern')
        self.broadcast_event = broadcast_event
        self._init_database()
    
    def _init_database(self):
        """Initialize all database tables"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # Settings table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            ''')
            
            # Staff table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS staff (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    position TEXT DEFAULT 'Specialist',
                    active BOOLEAN DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            ''')
            
            # Knowledge base table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS knowledge_base (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,  -- 'document' or 'link'
                    name TEXT NOT NULL,
                    description TEXT,
                    url TEXT,  -- For links
                    file_path TEXT,  -- For documents
                    content TEXT,  -- Extracted text content
                    embeddings TEXT,  -- JSON string of embeddings
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            ''')
            
            # Calls table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    call_control_id TEXT UNIQUE NOT NULL,
                    caller_phone TEXT NOT NULL,
                    called_phone TEXT NOT NULL,
                    customer_name TEXT,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    duration INTEGER,  -- in seconds
                    transcript TEXT,  -- JSON string of full conversation
                    summary TEXT,  -- AI-generated summary
                    status TEXT DEFAULT 'active',  -- 'active', 'completed', 'missed'
                    created_at TEXT NOT NULL
                )
            ''')
            
            # Messages table - UPDATED with last_summary_message_count and last_notification_analysis_timestamp
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,  -- phone number based
                    customer_phone TEXT NOT NULL,
                    business_phone TEXT NOT NULL,
                    customer_name TEXT,
                    messages TEXT NOT NULL,  -- JSON string of message history
                    summary TEXT,  -- AI-generated summary
                    last_message_time TEXT NOT NULL,
                    last_summary_message_count INTEGER DEFAULT 0,  -- Track when summary was last generated
                    last_notification_analysis_timestamp TEXT,  -- NEW: Track notification analysis cutoff point
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            ''')
            
            # Message templates table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS message_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_type TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    message_content TEXT NOT NULL,
                    is_enabled BOOLEAN DEFAULT 1,
                    max_chars INTEGER DEFAULT 160,
                    conditions TEXT,  -- JSON string of conditional settings
                    position TEXT,  -- JSON string of box position {x, y}
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            ''')
            
            # Add the new columns if they don't exist (for existing databases)
            cursor.execute('''
                SELECT name FROM pragma_table_info('messages') WHERE name='last_summary_message_count'
            ''')
            if not cursor.fetchone():
                cursor.execute('''
                    ALTER TABLE messages ADD COLUMN last_summary_message_count INTEGER DEFAULT 0
                ''')
                logger.info("✅ Added last_summary_message_count column to messages table")
            
            cursor.execute('''
                SELECT name FROM pragma_table_info('messages') WHERE name='last_notification_analysis_timestamp'
            ''')
            if not cursor.fetchone():
                cursor.execute('''
                    ALTER TABLE messages ADD COLUMN last_notification_analysis_timestamp TEXT
                ''')
                logger.info("✅ Added last_notification_analysis_timestamp column to messages table")
            
            # Add is_business_hours column to calls table if it doesn't exist
            cursor.execute('''
                SELECT name FROM pragma_table_info('calls') WHERE name='is_business_hours'
            ''')
            if not cursor.fetchone():
                cursor.execute('''
                    ALTER TABLE calls ADD COLUMN is_business_hours BOOLEAN DEFAULT 0
                ''')
                logger.info("✅ Added is_business_hours column to calls table")
            
            # Notifications table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,  -- 'critical', 'urgent', 'interest'
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    customer_name TEXT,
                    conversation_type TEXT NOT NULL,  -- 'voice' or 'sms'
                    conversation_id TEXT NOT NULL,  -- reference to call or message
                    resolved BOOLEAN DEFAULT 0,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                )
            ''')
            
            # Appointments table (expanded for full appointment details)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS appointments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    calendar_event_id TEXT UNIQUE,
                    customer_name TEXT,
                    customer_phone TEXT,
                    service TEXT,
                    service_name TEXT,
                    specialist TEXT,
                    appointment_date TEXT,
                    appointment_time TEXT,
                    price REAL,
                    duration INTEGER,
                    event_url TEXT,
                    status TEXT DEFAULT 'confirmed',
                    deposit_required BOOLEAN DEFAULT 0,
                    deposit_amount REAL,
                    payment_url TEXT,
                    payment_link_id TEXT,
                    messages_scheduled BOOLEAN,
                    scheduled_messages TEXT,
                    message_scheduling_error TEXT,
                    created_at TEXT
                )
            ''')
            
            # Customers table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS customers (
                    phone_number TEXT PRIMARY KEY,
                    name TEXT,
                    email TEXT,
                    profile_picture_path TEXT,
                    notes TEXT,  -- General notes about the customer
                    up_next_from_you TEXT,  -- Staff note for next expected service
                    total_appointments INTEGER DEFAULT 0,
                    last_appointment_date TEXT,
                    customer_since TEXT,  -- When they first became a customer
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            ''')
            
            # Appointment notes table (for staff notes on specific appointments)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS appointment_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    appointment_id INTEGER,
                    calendar_event_id TEXT,  -- Alternative reference for calendar events
                    customer_phone TEXT NOT NULL,
                    notes TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (appointment_id) REFERENCES appointments (id),
                    FOREIGN KEY (customer_phone) REFERENCES customers (phone_number)
                )
            ''')
            
            # Migrate appointments table if needed (add missing columns)
            self._migrate_appointments_table(cursor)
            conn.execute('PRAGMA journal_mode=WAL;')
            
            # Services table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS services (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    price REAL NOT NULL,
                    duration INTEGER NOT NULL,
                    requires_deposit BOOLEAN DEFAULT 1,
                    deposit_amount REAL DEFAULT 50,
                    description TEXT,
                    source_doc_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            ''')
            
            conn.commit()
            conn.close()
            
            # Initialize default settings
            self._init_default_settings()
            self._init_default_staff()
            
            logger.info("✅ Database initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Error initializing database: {str(e)}")
            raise
    
    def _init_default_settings(self):
        """Initialize default settings if they don't exist"""
        default_settings = {
            'business_hours_override': '',  # '', 'business', or 'after_hours'
            'ai_operating_hours': json.dumps({
                'Monday': {'start': '09:00', 'end': '16:00'},
                'Tuesday': {'start': '09:00', 'end': '16:00'},
                'Wednesday': {'start': '09:00', 'end': '16:00'},
                'Thursday': {'start': '09:00', 'end': '16:00'},
                'Friday': {'start': '09:00', 'end': '16:00'},
                'Saturday': {'start': '09:00', 'end': '15:00'},
                'Sunday': {'start': None, 'end': None}
            })
        }
        
        for key, value in default_settings.items():
            if not self.get_setting(key):
                self.set_setting(key, value)
    
    def _init_default_staff(self):
        """Initialize default staff if none exist"""
        if not self.get_all_staff():
            default_staff = [
                {'name': 'Sarah', 'position': 'Specialist'},
                {'name': 'Kennedy', 'position': 'Specialist'},
                {'name': 'Julia', 'position': 'Specialist'}
            ]
            
            for staff_member in default_staff:
                self.add_staff_member(staff_member['name'], staff_member['position'])
    
    def _migrate_appointments_table(self, cursor):
        """Migrate appointments table to add missing columns if needed"""
        try:
            # Get current columns in appointments table
            cursor.execute("PRAGMA table_info(appointments)")
            existing_columns = [row[1] for row in cursor.fetchall()]
            
            # Define required columns and their types
            required_columns = {
                'price': 'REAL',
                'service_name': 'TEXT',
                'duration': 'INTEGER',
                'event_url': 'TEXT',
                'status': 'TEXT DEFAULT "confirmed"',
                'deposit_required': 'BOOLEAN DEFAULT 0',
                'deposit_amount': 'REAL',
                'payment_url': 'TEXT',
                'payment_link_id': 'TEXT',
                'messages_scheduled': 'BOOLEAN',
                'scheduled_messages': 'TEXT',
                'message_scheduling_error': 'TEXT',
                'created_at': 'TEXT'
            }
            
            # Check which columns are missing
            missing_columns = []
            for column_name, column_type in required_columns.items():
                if column_name not in existing_columns:
                    missing_columns.append((column_name, column_type))
            
            if missing_columns:
                logger.info(f"🔧 Migrating appointments table: adding {len(missing_columns)} missing columns...")
                for column_name, column_type in missing_columns:
                    try:
                        cursor.execute(f"ALTER TABLE appointments ADD COLUMN {column_name} {column_type}")
                        logger.info(f"✅ Added column: {column_name} ({column_type})")
                    except Exception as e:
                        logger.error(f"❌ Failed to add column {column_name}: {str(e)}")
                logger.info("✅ Appointments table migration completed")
            else:
                logger.info("✅ Appointments table is up to date")
                
        except Exception as e:
            logger.error(f"❌ Error migrating appointments table: {str(e)}")
    
    # Settings CRUD operations
    def get_setting(self, key: str) -> Optional[str]:
        """Get a setting value by key"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
            result = cursor.fetchone()
            conn.close()
            
            return result[0] if result else None
            
        except Exception as e:
            logger.error(f"❌ Error getting setting {key}: {str(e)}")
            return None
    
    def set_setting(self, key: str, value: str) -> bool:
        """Set a setting value"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            now = datetime.now(self.timezone).isoformat()
            
            cursor.execute('''
                INSERT OR REPLACE INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
            ''', (key, value, now))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Setting {key} updated")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error setting {key}: {str(e)}")
            return False
    
    # Staff CRUD operations
    def get_all_staff(self, include_inactive=True):
        """Get all staff members"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            if include_inactive:
                cursor.execute("SELECT id, name, position, active FROM staff")
            else:
                cursor.execute("SELECT id, name, position, active FROM staff WHERE active = 1")
            
            rows = cursor.fetchall()
            conn.close()
            
            staff_list = []
            for row in rows:
                staff_list.append({
                    'id': row[0],
                    'name': row[1],
                    'position': row[2] if row[2] else 'Specialist',
                    'active': bool(row[3])
                })
            
            return staff_list
            
        except Exception as e:
            logger.error(f"❌ Error getting staff: {str(e)}")
            return []
    
    def get_active_staff_names(self):
        """Get list of active staff member names only - for priority staff management"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM staff WHERE active = 1")
            staff = cursor.fetchall()
            conn.close()
            return [row[0] for row in staff]
        except Exception as e:
            logger.error(f"❌ Error getting active staff names: {str(e)}")
            return []
    
    def add_staff_member(self, name, position='Specialist', active=True):
        """Add a new staff member"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            now = datetime.now(self.timezone).isoformat()
            
            cursor.execute('''
                INSERT INTO staff (name, position, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (name, position, int(active), now, now))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Staff member {name} added")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error adding staff member {name}: {str(e)}")
            return False
    
    def update_staff_member(self, staff_id, name=None, position=None, active=None):
        """Update a staff member"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            now = datetime.now(self.timezone).isoformat()
            
            updates = []
            params = []
            if name is not None:
                updates.append("name = ?")
                params.append(name)
            if position is not None:
                updates.append("position = ?")
                params.append(position)
            if active is not None:
                updates.append("active = ?")
                params.append(int(active))
            params.append(staff_id)
            
            cursor.execute(f"UPDATE staff SET {', '.join(updates)} WHERE id = ?", params)
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Staff member {staff_id} updated")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error updating staff member {staff_id}: {str(e)}")
            return False
    
    def remove_staff_member(self, staff_id: int) -> bool:
        """Remove (delete) a staff member"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM staff WHERE id = ?', (staff_id,))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Staff member {staff_id} removed")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error removing staff member {staff_id}: {str(e)}")
            return False
    
    # Knowledge base CRUD operations
    def get_all_knowledge_base_items(self) -> List[Dict]:
        """Get all knowledge base items"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, type, name, description, url, file_path, created_at, updated_at
                FROM knowledge_base
                ORDER BY created_at DESC
            ''')
            
            rows = cursor.fetchall()
            conn.close()
            
            items = []
            for row in rows:
                items.append({
                    'id': row[0],
                    'type': row[1],
                    'name': row[2],
                    'description': row[3],
                    'url': row[4],
                    'file_path': row[5],
                    'created_at': row[6],
                    'updated_at': row[7]
                })
            
            return items
            
        except Exception as e:
            logger.error(f"❌ Error getting knowledge base items: {str(e)}")
            return []
    
    def add_knowledge_base_item(self, item_type: str, name: str, description: str = None, 
                               url: str = None, file_path: str = None, content: str = None) -> bool:
        """Add a new knowledge base item"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            now = datetime.now(self.timezone).isoformat()
            
            cursor.execute('''
                INSERT INTO knowledge_base 
                (type, name, description, url, file_path, content, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (item_type, name, description, url, file_path, content, now, now))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Knowledge base item {name} added")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error adding knowledge base item {name}: {str(e)}")
            return False
    
    def remove_knowledge_base_item(self, item_id: int) -> bool:
        """Remove a knowledge base item"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM knowledge_base WHERE id = ?', (item_id,))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Knowledge base item {item_id} removed")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error removing knowledge base item {item_id}: {str(e)}")
            return False
    
    # Call logging operations
    def start_call_logging(self, call_control_id: str, caller_phone: str, called_phone: str, is_business_hours: bool = False) -> bool:
        """Start logging a new call with business hours tracking"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            now = datetime.now(self.timezone).isoformat()
            
            cursor.execute('''
                INSERT OR REPLACE INTO calls 
                (call_control_id, caller_phone, called_phone, start_time, status, is_business_hours, created_at)
                VALUES (?, ?, ?, ?, 'active', ?, ?)
            ''', (call_control_id, caller_phone, called_phone, now, is_business_hours, now))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Call logging started for {call_control_id} (business_hours: {is_business_hours})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error starting call logging: {str(e)}")
            return False
    
    def end_call_logging(self, call_control_id: str, transcript: List[Dict], 
                        customer_name: str = None, status: str = 'completed') -> bool:
        """End call logging with transcript"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            now = datetime.now(self.timezone).isoformat()
            transcript_json = json.dumps(transcript)
            
            # Calculate duration if we have start time
            cursor.execute('SELECT start_time FROM calls WHERE call_control_id = ?', (call_control_id,))
            result = cursor.fetchone()
            
            duration = None
            if result:
                start_time = datetime.fromisoformat(result[0])
                end_time = datetime.now(self.timezone)
                duration = int((end_time - start_time).total_seconds())
            
            cursor.execute('''
                UPDATE calls
                SET end_time = ?, duration = ?, transcript = ?, customer_name = ?, status = ?
                WHERE call_control_id = ?
            ''', (now, duration, transcript_json, customer_name, status, call_control_id))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Call logging ended for {call_control_id}")
            # Broadcast SSE event if available
            logger.info(f"[SSE] Attempting to broadcast call_finished for {call_control_id} (broadcast_event is {'set' if self.broadcast_event else 'None'})")
            if self.broadcast_event:
                try:
                    self.broadcast_event(f'{{"type": "call_finished", "callId": "{call_control_id}"}}')
                    logger.info(f"[SSE] Broadcasted call_finished for {call_control_id}")
                except Exception as e:
                    logger.error(f"❌ Error broadcasting call_finished SSE: {str(e)}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error ending call logging: {str(e)}")
            return False

    def get_calls_by_date_range(self, start_date: str, end_date: str) -> List[Dict]:
        """Get calls within a date range"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT call_control_id, caller_phone, called_phone, customer_name,
                       start_time, end_time, duration, status, created_at, transcript, summary, is_business_hours
                FROM calls
                WHERE start_time >= ? AND start_time <= ?
                ORDER BY start_time DESC
            ''', (start_date, end_date))
            
            rows = cursor.fetchall()
            conn.close()
            
            calls = []
            for row in rows:
                calls.append({
                    'call_control_id': row[0],
                    'caller_phone': row[1],
                    'called_phone': row[2],
                    'customer_name': row[3],
                    'start_time': row[4],
                    'end_time': row[5],
                    'duration': row[6],
                    'status': row[7],
                    'created_at': row[8],
                    'transcript': row[9],
                    'summary': row[10],
                    'is_business_hours': bool(row[11]) if row[11] is not None else False
                })
            
            return calls
            
        except Exception as e:
            logger.error(f"❌ Error getting calls by date range: {str(e)}")
            return []
    
    def get_call_by_id(self, call_control_id: str) -> Optional[Dict]:
        """Get a specific call by its control ID"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT call_control_id, caller_phone, called_phone, customer_name,
                       start_time, end_time, duration, status, created_at, transcript, summary, is_business_hours
                FROM calls
                WHERE call_control_id = ?
            ''', (call_control_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    'call_control_id': row[0],
                    'caller_phone': row[1],
                    'called_phone': row[2],
                    'customer_name': row[3],
                    'start_time': row[4],
                    'end_time': row[5],
                    'duration': row[6],
                    'status': row[7],
                    'created_at': row[8],
                    'transcript': row[9],
                    'summary': row[10],
                    'is_business_hours': bool(row[11]) if row[11] is not None else False
                }
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting call by ID {call_control_id}: {str(e)}")
            return None

    # Message logging operations - UPDATED with new functionality
    def log_message_exchange(self, customer_phone: str, business_phone: str, 
                           user_message: str, ai_response: str, customer_name: str = None) -> bool:
        """Log a message exchange"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            conversation_id = customer_phone  # Use phone as conversation ID
            now = datetime.now(self.timezone).isoformat()
            
            # Check if conversation exists
            cursor.execute('''
                SELECT messages, customer_name, last_summary_message_count, last_notification_analysis_timestamp, created_at FROM messages WHERE conversation_id = ?
            ''', (conversation_id,))
            
            result = cursor.fetchone()
            
            if result:
                # Update existing conversation
                existing_messages = json.loads(result[0])
                existing_customer_name = result[1]
                existing_summary_count = result[2] or 0
                existing_notification_timestamp = result[3]
                existing_created_at = result[4]
                
                # Add new messages
                if user_message:  # Only add user message if it's not empty (for manual sends)
                    existing_messages.append({
                        'sender': 'customer',
                        'message': user_message,
                        'timestamp': now
                    })
                
                existing_messages.append({
                    'sender': 'ai',
                    'message': ai_response,
                    'timestamp': now
                })
                
                # Update customer name if we have a new one
                final_customer_name = customer_name or existing_customer_name or ''
                
                # FIX: Check if conversation was created on a previous day
                # If so, update created_at to current time so it appears in today's messages
                should_update_created_at = False
                if existing_created_at:
                    try:
                        existing_date = datetime.fromisoformat(existing_created_at.replace('Z', '+00:00')).date()
                        current_date = datetime.fromisoformat(now.replace('Z', '+00:00')).date()
                        if existing_date < current_date:
                            should_update_created_at = True
                            logger.info(f"🔄 Updating created_at for conversation {conversation_id} from {existing_date} to today")
                    except Exception as e:
                        logger.warning(f"⚠️ Could not parse existing created_at date: {e}")
                
                if should_update_created_at:
                    cursor.execute('''
                        UPDATE messages
                        SET messages = ?, customer_name = ?, last_message_time = ?, updated_at = ?, created_at = ?
                        WHERE conversation_id = ?
                    ''', (json.dumps(existing_messages), final_customer_name, now, now, now, conversation_id))
                else:
                    cursor.execute('''
                        UPDATE messages
                        SET messages = ?, customer_name = ?, last_message_time = ?, updated_at = ?
                        WHERE conversation_id = ?
                    ''', (json.dumps(existing_messages), final_customer_name, now, now, conversation_id))
                
            else:
                # Create new conversation
                messages = []
                
                if user_message:  # Only add user message if it's not empty
                    messages.append({
                        'sender': 'customer',
                        'message': user_message,
                        'timestamp': now
                    })
                
                messages.append({
                    'sender': 'ai',
                    'message': ai_response,
                    'timestamp': now
                })
                
                cursor.execute('''
                    INSERT INTO messages
                    (conversation_id, customer_phone, business_phone, customer_name, 
                     messages, last_message_time, last_summary_message_count, last_notification_analysis_timestamp, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                ''', (conversation_id, customer_phone, business_phone, customer_name or '',
                      json.dumps(messages), now, now, now, now))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Message exchange logged for {customer_phone}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error logging message exchange: {str(e)}")
            return False
    
    def get_conversations_by_date_range(self, start_date: str, end_date: str) -> List[Dict]:
        """Get conversations within a date range"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT conversation_id, customer_phone, business_phone, customer_name,
                       messages, last_message_time, created_at, updated_at, summary, last_summary_message_count, last_notification_analysis_timestamp
                FROM messages
                WHERE created_at >= ? AND created_at <= ?
                ORDER BY last_message_time DESC
            ''', (start_date, end_date))
            
            rows = cursor.fetchall()
            conn.close()
            
            conversations = []
            for row in rows:
                conversations.append({
                    'conversation_id': row[0],
                    'customer_phone': row[1],
                    'business_phone': row[2],
                    'customer_name': row[3],
                    'messages': row[4],  # JSON string
                    'last_message_time': row[5],
                    'created_at': row[6],
                    'updated_at': row[7],
                    'summary': row[8],
                    'last_summary_message_count': row[9] or 0,
                    'last_notification_analysis_timestamp': row[10]
                })
            
            return conversations
            
        except Exception as e:
            logger.error(f"❌ Error getting conversations by date range: {str(e)}")
            return []
    
    def get_conversation_by_id(self, conversation_id: str) -> Optional[Dict]:
        """Get a specific conversation by its ID"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT conversation_id, customer_phone, business_phone, customer_name,
                       messages, last_message_time, created_at, updated_at, summary, last_summary_message_count, last_notification_analysis_timestamp
                FROM messages
                WHERE conversation_id = ?
            ''', (conversation_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    'conversation_id': row[0],
                    'customer_phone': row[1],
                    'business_phone': row[2],
                    'customer_name': row[3],
                    'messages': row[4],  # JSON string
                    'last_message_time': row[5],
                    'created_at': row[6],
                    'updated_at': row[7],
                    'summary': row[8],
                    'last_summary_message_count': row[9] or 0,
                    'last_notification_analysis_timestamp': row[10]
                }
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting conversation by ID {conversation_id}: {str(e)}")
            return None
    
    def update_conversation_summary(self, conversation_id: str, summary: str) -> bool:
        """Update conversation summary"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            now = datetime.now(self.timezone).isoformat()
            
            cursor.execute('''
                UPDATE messages
                SET summary = ?, updated_at = ?
                WHERE conversation_id = ?
            ''', (summary, now, conversation_id))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Summary updated for conversation {conversation_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error updating conversation summary: {str(e)}")
            return False
    
    def update_conversation_message_count_for_summary(self, conversation_id: str, count: int) -> bool:
        """Update the message count when summary was last generated"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            now = datetime.now(self.timezone).isoformat()
            
            cursor.execute('''
                UPDATE messages
                SET last_summary_message_count = ?, updated_at = ?
                WHERE conversation_id = ?
            ''', (count, now, conversation_id))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Summary message count updated for conversation {conversation_id}: {count}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error updating summary message count: {str(e)}")
            return False
    
    def update_conversation_customer_name(self, conversation_id: str, name: str) -> bool:
        """Update the customer name for a conversation"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            now = datetime.now(self.timezone).isoformat()
            
            cursor.execute('''
                UPDATE messages 
                SET customer_name = ?, updated_at = ?
                WHERE conversation_id = ?
            ''', (name, now, conversation_id))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Updated conversation name for {conversation_id}: {name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error updating conversation name: {str(e)}")
            return False
    
    def update_notification_analysis_timestamp(self, conversation_id: str, timestamp: str) -> bool:
        """Update the last notification analysis timestamp for a conversation"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            now = datetime.now(self.timezone).isoformat()
            
            cursor.execute('''
                UPDATE messages
                SET last_notification_analysis_timestamp = ?, updated_at = ?
                WHERE conversation_id = ?
            ''', (timestamp, now, conversation_id))
            
            conn.commit()
            conn.close()
            
            logger.info(f"🔄 Updated notification analysis timestamp for conversation {conversation_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error updating notification analysis timestamp: {str(e)}")
            return False
    
    # Appointment logging operations
    def log_appointment_creation(self, calendar_event_id: str, customer_name: str, 
                               customer_phone: str, service: str, specialist: str,
                               appointment_date: str, appointment_time: str) -> bool:
        """Log when an appointment is created"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            now = datetime.now(self.timezone).isoformat()
            
            cursor.execute('''
                INSERT OR REPLACE INTO appointments
                (calendar_event_id, customer_name, customer_phone, service, 
                 specialist, appointment_date, appointment_time, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (calendar_event_id, customer_name, customer_phone, service,
                  specialist, appointment_date, appointment_time, now))
            
            # Update customer statistics after logging appointment
            self._update_customer_stats(cursor, customer_phone)
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Appointment creation logged: {calendar_event_id}")
            if self.broadcast_event:
                self.broadcast_event('{"type": "appointment_created"}')
            return True
            
        except Exception as e:
            logger.error(f"❌ Error logging appointment creation: {str(e)}")
            return False
    
    def get_appointments_by_date_range(self, start_date: str, end_date: str) -> List[Dict]:
        """Get appointments created within a date range"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT calendar_event_id, customer_name, customer_phone, service,
                       specialist, appointment_date, appointment_time, created_at
                FROM appointments
                WHERE created_at >= ? AND created_at <= ? AND status != ?
                ORDER BY created_at DESC
            ''', (start_date, end_date, 'cancelled'))
            
            rows = cursor.fetchall()
            conn.close()
            
            appointments = []
            for row in rows:
                appointments.append({
                    'calendar_event_id': row[0],
                    'customer_name': row[1],
                    'customer_phone': row[2],
                    'service': row[3],
                    'specialist': row[4],
                    'appointment_date': row[5],
                    'appointment_time': row[6],
                    'created_at': row[7]
                })
            
            return appointments
            
        except Exception as e:
            logger.error(f"❌ Error getting appointments by date range: {str(e)}")
            return []
    
    # Notification operations - UPDATED with replacement instead of blocking
    def check_existing_notification(self, phone: str, notification_type: str, conversation_type: str) -> Optional[int]:
        """Check if an unresolved notification of the same type already exists for this phone/conversation type
        Returns the notification ID if found, None otherwise"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id FROM notifications
                WHERE phone = ? AND type = ? AND conversation_type = ? AND resolved = 0
            ''', (phone, notification_type, conversation_type))
            
            result = cursor.fetchone()
            conn.close()
            
            return result[0] if result else None
            
        except Exception as e:
            logger.error(f"❌ Error checking existing notification: {str(e)}")
            return None
    
    def replace_existing_notification(self, notification_id: int, notification_type: str, title: str, summary: str,
                                    phone: str, customer_name: str, conversation_type: str,
                                    conversation_id: str) -> bool:
        """Replace an existing notification with updated information"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            now = datetime.now(self.timezone).isoformat()
            
            cursor.execute('''
                UPDATE notifications
                SET title = ?, summary = ?, customer_name = ?, conversation_id = ?, created_at = ?
                WHERE id = ?
            ''', (title, summary, customer_name, conversation_id, now, notification_id))
            
            conn.commit()
            conn.close()
            
            logger.info(f"🔄 Notification replaced: {title} (ID: {notification_id})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error replacing notification: {str(e)}")
            return False
    
    def create_notification(self, notification_type: str, title: str, summary: str,
                          phone: str, customer_name: str, conversation_type: str,
                          conversation_id: str) -> bool:
        """Create a new notification with replacement logic instead of blocking"""
        try:
            # Check if an unresolved notification of the same type already exists
            existing_notification_id = self.check_existing_notification(phone, notification_type, conversation_type)
            
            if existing_notification_id:
                # Replace the existing notification with updated information
                logger.info(f"🔄 Replacing existing notification: {notification_type} for {phone} ({conversation_type})")
                return self.replace_existing_notification(
                    existing_notification_id, notification_type, title, summary,
                    phone, customer_name, conversation_type, conversation_id
                )
            
            # No existing notification found, create a new one
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            now = datetime.now(self.timezone).isoformat()
            
            cursor.execute('''
                INSERT INTO notifications
                (type, title, summary, phone, customer_name, conversation_type, 
                 conversation_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (notification_type, title, summary, phone, customer_name,
                  conversation_type, conversation_id, now))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ New notification created: {title}")
            if self.broadcast_event:
                self.broadcast_event('{"type": "notification_created"}')
            return True
            
        except Exception as e:
            logger.error(f"❌ Error creating notification: {str(e)}")
            return False
    
    def get_all_notifications(self) -> List[Dict]:
        """Get all notifications"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, type, title, summary, phone, customer_name,
                       conversation_type, conversation_id, resolved, created_at, resolved_at
                FROM notifications
                ORDER BY created_at DESC
            ''')
            
            rows = cursor.fetchall()
            conn.close()
            
            notifications = []
            for row in rows:
                notifications.append({
                    'id': row[0],
                    'type': row[1],
                    'title': row[2],
                    'summary': row[3],
                    'phone': row[4],
                    'customer_name': row[5],
                    'conversation_type': row[6],
                    'conversation_id': row[7],
                    'resolved': bool(row[8]),
                    'created_at': row[9],
                    'resolved_at': row[10]
                })
            
            return notifications
            
        except Exception as e:
            logger.error(f"❌ Error getting notifications: {str(e)}")
            return []
    
    def resolve_notification(self, notification_id: int) -> bool:
        """Mark a notification as resolved and update conversation analysis timestamp - FIXED: Set timestamp to current time"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            now = datetime.now(self.timezone).isoformat()
            
            # Get notification details first
            cursor.execute('''
                SELECT conversation_id, conversation_type FROM notifications
                WHERE id = ?
            ''', (notification_id,))
            
            notification_data = cursor.fetchone()
            
            if notification_data:
                conversation_id, conversation_type = notification_data
                
                # Mark notification as resolved
                cursor.execute('''
                    UPDATE notifications
                    SET resolved = 1, resolved_at = ?
                    WHERE id = ?
                ''', (now, notification_id))
                
                # FIXED: Update conversation analysis timestamp to current time for SMS conversations
                # This ensures future analysis only looks at messages after resolution
                if conversation_type == 'sms':
                    cursor.execute('''
                        UPDATE messages
                        SET last_notification_analysis_timestamp = ?, updated_at = ?
                        WHERE conversation_id = ?
                    ''', (now, now, conversation_id))
                    logger.info(f"🔄 Updated notification analysis timestamp for conversation {conversation_id} to current time")
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Notification {notification_id} resolved")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error resolving notification: {str(e)}")
            return False
    
    def delete_notification(self, notification_id: int) -> bool:
        """Delete a notification"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM notifications WHERE id = ?', (notification_id,))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Notification {notification_id} deleted")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error deleting notification: {str(e)}")
            return False
    
    def get_interest_notifications_by_phone(self, phone: str) -> List[Dict]:
        """Get all unresolved interest notifications for a specific phone number"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, type, title, summary, phone, customer_name,
                       conversation_type, conversation_id, created_at
                FROM notifications
                WHERE phone = ? AND type = 'interest' AND resolved = 0
                ORDER BY created_at DESC
                ''', (phone,))
            
            rows = cursor.fetchall()
            conn.close()
            
            notifications = []
            for row in rows:
                notifications.append({
                    'id': row[0],
                    'type': row[1],
                    'title': row[2],
                    'summary': row[3],
                    'phone': row[4],
                    'customer_name': row[5],
                    'conversation_type': row[6],
                    'conversation_id': row[7],
                    'created_at': row[8]
                })
            
            logger.info(f"🔍 Found {len(notifications)} unresolved interest notifications for {phone}")
            return notifications
            
        except Exception as e:
            logger.error(f"❌ Error getting interest notifications: {str(e)}")
            return []

    def delete_interest_notifications_for_phone(self, phone: str) -> bool:
        """Delete all unresolved interest notifications for a specific phone number"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # Get count before deletion for logging
            cursor.execute('''
                SELECT COUNT(*) FROM notifications
                WHERE phone = ? AND type = 'interest' AND resolved = 0
            ''', (phone,))
            
            count = cursor.fetchone()[0]
            
            # Delete all unresolved interest notifications for this phone
            cursor.execute('''
                DELETE FROM notifications
                WHERE phone = ? AND type = 'interest' AND resolved = 0
            ''', (phone,))
            
            conn.commit()
            conn.close()
            
            if count > 0:
                logger.info(f"🗑️ Deleted {count} interest notifications for {phone}")
                if self.broadcast_event:
                    self.broadcast_event('{"type": "notification_deleted"}')
                else:
                    logger.info(f"ℹ️ No interest notifications found to delete for {phone}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error deleting interest notifications: {str(e)}")
            return False
    
    def update_conversation_analysis_timestamp_after_rescission(self, conversation_id: str, timestamp: str) -> bool:
        """Update conversation analysis timestamp after rescinding interest notifications to prevent re-analysis"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE messages
                SET last_notification_analysis_timestamp = ?, updated_at = ?
                WHERE conversation_id = ?
            ''', (timestamp, timestamp, conversation_id))
            
            conn.commit()
            conn.close()
            
            logger.info(f"🔄 Updated notification analysis timestamp for conversation {conversation_id} to {timestamp}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error updating conversation analysis timestamp: {str(e)}")
            return False

    def update_call_summary(self, call_control_id: str, summary: str) -> bool:
        """Update call summary"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            now = datetime.now(self.timezone).isoformat()
            cursor.execute('''
                UPDATE calls
                SET summary = ?, end_time = ?
                WHERE call_control_id = ?
            ''', (summary, now, call_control_id))
            conn.commit()
            conn.close()
            logger.info(f"✅ Summary updated for call {call_control_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Error updating call summary: {str(e)}")
            return False

    def close(self):
        """Close database connection (if needed for cleanup)"""
        pass

    def get_voice_calls_for_archiving(self) -> List[Dict]:
        """Get all voice calls from the last 24 hours for archiving."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            now = datetime.now(self.timezone)
            yesterday = now - timedelta(days=1)
            cursor.execute('''
                SELECT call_control_id, customer_name, caller_phone, start_time, end_time, duration, transcript, summary
                FROM calls
                WHERE start_time >= ?
            ''', (yesterday.isoformat(),))
            rows = cursor.fetchall()
            conn.close()
            calls = []
            for row in rows:
                transcript = []
                try:
                    transcript = json.loads(row[6]) if row[6] else []
                except Exception:
                    transcript = []
                calls.append({
                    'id': row[0],
                    'customer_name': row[1],
                    'phone': row[2],
                    'start_time': row[3],
                    'end_time': row[4],
                    'duration': row[5],
                    'transcript': transcript,
                    'ai_summary': row[7]
                })
            return calls
        except Exception as e:
            logger.error(f"❌ Error getting voice calls for archiving: {str(e)}")
            return []

    def clear_voice_calls_for_archiving(self) -> None:
        """Delete all voice calls from the last 24 hours after archiving, except those referenced by unresolved notifications."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            now = datetime.now(self.timezone)
            yesterday = now - timedelta(days=1)
            # Get all call_control_ids referenced by unresolved notifications
            cursor.execute('''
                SELECT conversation_id FROM notifications WHERE resolved = 0 AND conversation_type = 'voice'
            ''')
            protected_ids = set(row[0] for row in cursor.fetchall())
            # Get all calls in the last 24 hours
            cursor.execute('''
                SELECT call_control_id FROM calls WHERE start_time >= ?
            ''', (yesterday.isoformat(),))
            call_ids = [row[0] for row in cursor.fetchall()]
            # Only delete those not referenced
            to_delete = [cid for cid in call_ids if cid not in protected_ids]
            for cid in to_delete:
                cursor.execute('DELETE FROM calls WHERE call_control_id = ?', (cid,))
            conn.commit()
            conn.close()
            logger.info(f"✅ Cleared voice calls for archiving (preserved {len(protected_ids)} referenced by notifications)")
        except Exception as e:
            logger.error(f"❌ Error clearing voice calls for archiving: {str(e)}")

    def get_messages_for_archiving(self) -> List[Dict]:
        """Get all messages from the last 24 hours for archiving."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            now = datetime.now(self.timezone)
            yesterday = now - timedelta(days=1)
            cursor.execute('''
                SELECT conversation_id, customer_name, customer_phone, created_at, updated_at, messages, summary
                FROM messages
                WHERE created_at >= ?
            ''', (yesterday.isoformat(),))
            rows = cursor.fetchall()
            conn.close()
            messages = []
            for row in rows:
                transcript = []
                try:
                    transcript = json.loads(row[5]) if row[5] else []
                except Exception:
                    transcript = []
                messages.append({
                    'id': row[0],
                    'customer_name': row[1],
                    'phone': row[2],
                    'start_time': row[3],
                    'end_time': row[4],
                    'transcript': transcript,
                    'ai_summary': row[6]
                })
            return messages
        except Exception as e:
            logger.error(f"❌ Error getting messages for archiving: {str(e)}")
            return []

    def clear_messages_for_archiving(self) -> None:
        """Delete all messages from the last 24 hours after archiving, except those referenced by unresolved notifications."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            now = datetime.now(self.timezone)
            yesterday = now - timedelta(days=1)
            # Get all conversation_ids referenced by unresolved notifications
            cursor.execute('''
                SELECT conversation_id FROM notifications WHERE resolved = 0 AND conversation_type = 'sms'
            ''')
            protected_ids = set(row[0] for row in cursor.fetchall())
            # Get all messages in the last 24 hours
            cursor.execute('''
                SELECT conversation_id FROM messages WHERE created_at >= ?
            ''', (yesterday.isoformat(),))
            msg_ids = [row[0] for row in cursor.fetchall()]
            # Only delete those not referenced
            to_delete = [cid for cid in msg_ids if cid not in protected_ids]
            for cid in to_delete:
                cursor.execute('DELETE FROM messages WHERE conversation_id = ?', (cid,))
            conn.commit()
            conn.close()
            logger.info(f"✅ Cleared messages for archiving (preserved {len(protected_ids)} referenced by notifications)")
        except Exception as e:
            logger.error(f"❌ Error clearing messages for archiving: {str(e)}")

    def get_notifications_for_archiving(self) -> List[Dict]:
        """TEMP: Get all unresolved notifications for archiving, regardless of age (for testing)."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            # TEMP: Remove age filter, just unresolved
            cursor.execute('''
                SELECT id, type, title, phone, conversation_id, created_at, resolved, resolved_at, summary
                FROM notifications
                WHERE resolved = 0
            ''')
            rows = cursor.fetchall()
            conn.close()
            notifications = []
            for row in rows:
                notifications.append({
                    'id': row[0],
                    'type': row[1],
                    'title': row[2],
                    'phone': row[3],
                    'conversation_id': row[4],
                    'created_at': row[5],
                    'resolved': row[6],
                    'resolved_at': row[7],
                    'summary': row[8]
                })
            return notifications
        except Exception as e:
            logger.error(f"❌ Error getting notifications for archiving: {str(e)}")
            return []

    def clear_notifications_for_archiving(self) -> None:
        """Delete unresolved notifications older than 7 days after archiving (production logic)."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            now = datetime.now(self.timezone)
            week_ago = now - timedelta(days=7)
            cursor.execute('''
                DELETE FROM notifications WHERE resolved = 0 AND created_at <= ?
            ''', (week_ago.isoformat(),))
            conn.commit()
            conn.close()
            logger.info("✅ Cleared notifications for archiving (older than 7 days)")
        except Exception as e:
            logger.error(f"❌ Error clearing notifications for archiving: {str(e)}")

    def add_service(self, name, price, duration, requires_deposit=True, deposit_amount=50, description=None, source_doc_id=None):
        """Add a new service to the database"""
        now = datetime.now(self.timezone).isoformat()
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO services (name, price, duration, requires_deposit, deposit_amount, description, source_doc_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, price, duration, int(requires_deposit), deposit_amount, description, source_doc_id, now, now))
        conn.commit()
        conn.close()

    def get_services(self):
        """Retrieve all services from the database"""
        try:
            logger.info(f"🔧 Getting services from database: {self.db_file}")
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # Check if services table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='services'")
            table_exists = cursor.fetchone()
            if not table_exists:
                logger.error("❌ Services table does not exist!")
                conn.close()
                return []
            
            cursor.execute('SELECT id, name, price, duration, requires_deposit, deposit_amount, description, source_doc_id FROM services')
            rows = cursor.fetchall()
            conn.close()
            
            columns = ['id', 'name', 'price', 'duration', 'requires_deposit', 'deposit_amount', 'description', 'source_doc_id']
            services = [dict(zip(columns, row)) for row in rows]
            logger.info(f"✅ Retrieved {len(services)} services from database")
            return services
            
        except Exception as e:
            logger.error(f"❌ Error in get_services: {str(e)}")
            logger.error(f"❌ Error type: {type(e).__name__}")
            return []

    def get_service_by_id(self, service_id):
        """Retrieve a single service by its ID"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, price, duration, requires_deposit, deposit_amount, description, source_doc_id FROM services WHERE id = ?', (service_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            columns = ['id', 'name', 'price', 'duration', 'requires_deposit', 'deposit_amount', 'description', 'source_doc_id']
            return dict(zip(columns, row))
        return None

    def update_service(self, service_id, name=None, price=None, duration=None, requires_deposit=None, deposit_amount=None, description=None):
        """Update an existing service"""
        now = datetime.now(self.timezone).isoformat()
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        # Build dynamic update query
        fields = []
        values = []
        if name is not None:
            fields.append('name = ?')
            values.append(name)
        if price is not None:
            fields.append('price = ?')
            values.append(price)
        if duration is not None:
            fields.append('duration = ?')
            values.append(duration)
        if requires_deposit is not None:
            fields.append('requires_deposit = ?')
            values.append(int(requires_deposit))
        if deposit_amount is not None:
            fields.append('deposit_amount = ?')
            values.append(deposit_amount)
        if description is not None:
            fields.append('description = ?')
            values.append(description)
        fields.append('updated_at = ?')
        values.append(now)
        values.append(service_id)
        query = f'UPDATE services SET {", ".join(fields)} WHERE id = ?'
        cursor.execute(query, values)
        conn.commit()
        conn.close()

    def delete_service(self, service_id):
        """Delete a service from the database"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM services WHERE id = ?', (service_id,))
        conn.commit()
        conn.close()

    def get_service_by_name(self, name):
        """Retrieve a single service by its name/key (case-insensitive)"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, price, duration, requires_deposit, deposit_amount, description, source_doc_id FROM services WHERE LOWER(name) = LOWER(?)', (name,))
        row = cursor.fetchone()
        conn.close()
        if row:
            columns = ['id', 'name', 'price', 'duration', 'requires_deposit', 'deposit_amount', 'description', 'source_doc_id']
            return dict(zip(columns, row))
        return None

    def create_appointment(self, appointment_data: dict) -> bool:
        """Create or update an appointment with all details."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            now = datetime.now(self.timezone).isoformat()
            # Check if appointment exists
            cursor.execute('SELECT id FROM appointments WHERE calendar_event_id = ?', (appointment_data.get('id') or appointment_data.get('calendar_event_id'),))
            exists = cursor.fetchone()
            if exists:
                # Update existing
                update_fields = {k: v for k, v in appointment_data.items() if k != 'id' and k != 'calendar_event_id'}
                if update_fields:
                    fields = ', '.join([f"{k} = ?" for k in update_fields.keys()])
                    values = list(update_fields.values())
                    values.append(appointment_data.get('id') or appointment_data.get('calendar_event_id'))
                    cursor.execute(f'UPDATE appointments SET {fields} WHERE calendar_event_id = ?', values)
            else:
                # Insert new
                cursor.execute('''
                    INSERT INTO appointments (
                        calendar_event_id, customer_name, customer_phone, service, service_name, specialist,
                        appointment_date, appointment_time, price, duration, event_url, status,
                        deposit_required, deposit_amount, payment_url, payment_link_id,
                        messages_scheduled, scheduled_messages, message_scheduling_error, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    appointment_data.get('id') or appointment_data.get('calendar_event_id'),
                    appointment_data.get('customer_name'),
                    appointment_data.get('customer_phone'),
                    appointment_data.get('service'),
                    appointment_data.get('service_name'),
                    appointment_data.get('specialist'),
                    appointment_data.get('appointment_date'),
                    appointment_data.get('appointment_time'),
                    appointment_data.get('price'),
                    appointment_data.get('duration'),
                    appointment_data.get('event_url'),
                    appointment_data.get('status', 'confirmed'),
                    int(appointment_data.get('deposit_required', False)) if appointment_data.get('deposit_required') is not None else None,
                    appointment_data.get('deposit_amount'),
                    appointment_data.get('payment_url'),
                    appointment_data.get('payment_link_id'),
                    int(appointment_data.get('messages_scheduled', False)) if appointment_data.get('messages_scheduled') is not None else None,
                    json.dumps(appointment_data.get('scheduled_messages')) if appointment_data.get('scheduled_messages') is not None else None,
                    appointment_data.get('message_scheduling_error'),
                    now
                ))
            conn.commit()
            conn.close()
            logger.info(f"✅ Appointment created/updated: {appointment_data.get('id') or appointment_data.get('calendar_event_id')}")
            return True
        except Exception as e:
            try:
                conn.rollback()
            except:
                pass
            logger.error(f"❌ Error creating/updating appointment: {str(e)}")
            return False

    def update_appointment(self, calendar_event_id: str, updated_data: dict) -> bool:
        """Update an appointment by calendar_event_id."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            fields = []
            values = []
            for k, v in updated_data.items():
                fields.append(f"{k} = ?")
                if k == 'scheduled_messages' and v is not None:
                    values.append(json.dumps(v))
                else:
                    values.append(v)
            values.append(calendar_event_id)
            query = f"UPDATE appointments SET {', '.join(fields)} WHERE calendar_event_id = ?"
            cursor.execute(query, values)
            conn.commit()
            conn.close()
            logger.info(f"✅ Appointment updated: {calendar_event_id}")
            return True
        except Exception as e:
            try:
                conn.rollback()
            except:
                pass
            logger.error(f"❌ Error updating appointment: {str(e)}")
            return False

    def get_appointment_by_id(self, calendar_event_id: str) -> Optional[dict]:
        """Get a single appointment by calendar_event_id."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM appointments WHERE calendar_event_id = ?', (calendar_event_id,))
            row = cursor.fetchone()
            conn.close()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None
        except Exception as e:
            logger.error(f"❌ Error getting appointment by id: {str(e)}")
            return None

    def get_appointments_by_phone(self, phone: str, only_upcoming: bool = True) -> list:
        """Get all (optionally only upcoming) appointments for a phone number."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            now = datetime.now(self.timezone).strftime('%Y-%m-%dT%H:%M')
            if only_upcoming:
                cursor.execute('''
                    SELECT * FROM appointments WHERE customer_phone = ? AND (appointment_date > ? OR (appointment_date = ? AND appointment_time >= ?)) AND status = 'confirmed' ORDER BY appointment_date, appointment_time
                ''', (phone, now[:10], now[:10], now[11:]))
            else:
                cursor.execute('''
                    SELECT * FROM appointments WHERE customer_phone = ? AND status != 'cancelled' ORDER BY appointment_date, appointment_time
                ''', (phone,))
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            conn.close()
            return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error(f"❌ Error getting appointments by phone: {str(e)}")
            return []

    def list_upcoming_appointments(self, phone: str) -> list:
        """Alias for get_appointments_by_phone with only_upcoming=True."""
        return self.get_appointments_by_phone(phone, only_upcoming=True)

    def update_appointment_notes(self, appointment_id: str, notes: str) -> bool:
        """Update notes for a specific appointment"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE appointments 
                SET notes = ?
                WHERE calendar_event_id = ? OR id = ?
            ''', (notes, appointment_id, appointment_id))
            
            conn.commit()
            conn.close()
            
            if cursor.rowcount > 0:
                logger.info(f"✅ Appointment notes updated for {appointment_id}")
                return True
            else:
                logger.warning(f"⚠️ No appointment found with ID {appointment_id}")
                return False
            
        except Exception as e:
            logger.error(f"❌ Error updating appointment notes: {str(e)}")
            return False

    # ==================== CUSTOMER MANAGEMENT METHODS ====================
    
    def create_customer(self, phone_number: str, name: str = None, email: str = None, 
                       notes: str = None, up_next_from_you: str = None) -> bool:
        """Create a new customer record"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            now = datetime.now(self.timezone).isoformat()
            
            cursor.execute('''
                INSERT INTO customers (
                    phone_number, name, email, notes, up_next_from_you, 
                    customer_since, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (phone_number, name, email, notes, up_next_from_you, now, now, now))
            
            # Update customer statistics
            self._update_customer_stats(cursor, phone_number)
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Customer created: {phone_number} - {name}")
            if self.broadcast_event:
                self.broadcast_event('{"type": "customer_created"}')
            return True
            
        except sqlite3.IntegrityError:
            logger.warning(f"⚠️ Customer already exists: {phone_number}")
            return False
        except Exception as e:
            logger.error(f"❌ Error creating customer: {str(e)}")
            return False
    
    def get_customer(self, phone_number: str) -> Optional[dict]:
        """Get a customer by phone number"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM customers WHERE phone_number = ?', (phone_number,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting customer: {str(e)}")
            return None
    
    def update_customer(self, phone_number: str, **kwargs) -> bool:
        """Update customer information"""
        try:
            if not kwargs:
                return True
                
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # Build dynamic update query
            fields = []
            values = []
            
            for field, value in kwargs.items():
                if field in ['name', 'email', 'profile_picture_path', 'notes', 'up_next_from_you']:
                    fields.append(f'{field} = ?')
                    values.append(value)
            
            if not fields:
                return True
                
            fields.append('updated_at = ?')
            values.append(datetime.now(self.timezone).isoformat())
            values.append(phone_number)
            
            query = f'UPDATE customers SET {", ".join(fields)} WHERE phone_number = ?'
            cursor.execute(query, values)
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Customer updated: {phone_number}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error updating customer: {str(e)}")
            return False
    
    def delete_customer(self, phone_number: str) -> bool:
        """Delete a customer (use with caution)"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM customers WHERE phone_number = ?', (phone_number,))
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Customer deleted: {phone_number}")
            if self.broadcast_event:
                self.broadcast_event('{"type": "customer_deleted"}')
            return True
            
        except Exception as e:
            logger.error(f"❌ Error deleting customer: {str(e)}")
            return False
    
    def list_customers(self, search: str = None, sort_by: str = 'name', 
                      sort_order: str = 'ASC', limit: int = None, refresh_stats: bool = True) -> dict:
        """List customers with optional search, sorting, and pagination. Returns dict with customers and total_count."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # Refresh customer stats to ensure data is current
            if refresh_stats:
                # Get all customer phone numbers that match the search criteria
                if search:
                    cursor.execute('''
                        SELECT phone_number FROM customers 
                        WHERE (name LIKE ? OR phone_number LIKE ? OR email LIKE ?)
                    ''', (f'%{search}%', f'%{search}%', f'%{search}%'))
                else:
                    cursor.execute('SELECT phone_number FROM customers')
                
                phone_numbers = [row[0] for row in cursor.fetchall()]
                
                # Update stats for each customer
                for phone_number in phone_numbers:
                    self._update_customer_stats(cursor, phone_number)
            
            # First, get total count (before applying limit)
            count_query = 'SELECT COUNT(*) FROM customers'
            count_params = []
            
            # Add search filter to count query
            if search:
                count_query += ' WHERE (name LIKE ? OR phone_number LIKE ? OR email LIKE ?)'
                search_param = f'%{search}%'
                count_params.extend([search_param, search_param, search_param])
            
            cursor.execute(count_query, count_params)
            total_count = cursor.fetchone()[0]
            
            # Base query for actual data
            query = 'SELECT * FROM customers'
            params = []
            
            # Add search filter
            if search:
                query += ' WHERE (name LIKE ? OR phone_number LIKE ? OR email LIKE ?)'
                search_param = f'%{search}%'
                params.extend([search_param, search_param, search_param])
            
            # Add sorting
            valid_sort_fields = ['name', 'phone_number', 'total_appointments', 
                               'last_appointment_date', 'created_at']
            if sort_by in valid_sort_fields:
                query += f' ORDER BY {sort_by} {sort_order.upper()}'
            else:
                query += ' ORDER BY name ASC'
            
            # Add limit
            if limit:
                query += f' LIMIT {limit}'
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            conn.close()
            
            customers = [dict(zip(columns, row)) for row in rows]
            
            return {
                'customers': customers,
                'total_count': total_count
            }
            
        except Exception as e:
            logger.error(f"❌ Error listing customers: {str(e)}")
            return {'customers': [], 'total_count': 0}
    
    def get_customer_with_appointments(self, phone_number: str) -> Optional[dict]:
        """Get customer with their full appointment history"""
        try:
            # First, refresh customer stats to ensure data is current
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            self._update_customer_stats(cursor, phone_number)
            conn.commit()
            conn.close()
            
            customer = self.get_customer(phone_number)
            if not customer:
                return None
            
            # Get all appointments for this customer
            appointments = self.get_appointments_by_phone(phone_number, only_upcoming=False)
            
            # Separate past and upcoming appointments
            now = datetime.now(self.timezone)
            past_appointments = []
            upcoming_appointments = []
            
            for apt in appointments:
                try:
                    apt_datetime_str = f"{apt['appointment_date']}T{apt['appointment_time']}"
                    # Parse as naive datetime first
                    apt_datetime_naive = datetime.fromisoformat(apt_datetime_str)
                    # Make it timezone-aware using the business timezone (Eastern)
                    apt_datetime = self.timezone.localize(apt_datetime_naive)
                    
                    if apt_datetime < now:
                        past_appointments.append(apt)
                    else:
                        upcoming_appointments.append(apt)
                except Exception as e:
                    logger.error(f"Error parsing appointment datetime: {apt.get('appointment_date')} {apt.get('appointment_time')} - {str(e)}")
                    # If parsing fails, assume it's upcoming
                    upcoming_appointments.append(apt)
            
            # Notes are now included directly in the appointments query
            
            customer['past_appointments'] = past_appointments
            customer['upcoming_appointments'] = upcoming_appointments
            customer['total_appointments'] = len(appointments)
            
            return customer
            
        except Exception as e:
            logger.error(f"❌ Error getting customer with appointments: {str(e)}")
            return None
    
    def _update_customer_stats(self, cursor, phone_number: str):
        """Update customer statistics (total appointments, last appointment date)"""
        try:
            # Count total appointments (exclude cancelled)
            cursor.execute(
                'SELECT COUNT(*) FROM appointments WHERE customer_phone = ? AND status != ?',
                (phone_number, 'cancelled')
            )
            total_count = cursor.fetchone()[0] or 0
            
            # Get the most recent PAST appointment (not future ones)
            now = datetime.now(self.timezone)
            current_date = now.strftime('%Y-%m-%d')
            current_time = now.strftime('%H:%M')
            
            cursor.execute('''
                SELECT appointment_date, appointment_time 
                FROM appointments 
                WHERE customer_phone = ? 
                AND (appointment_date < ? OR (appointment_date = ? AND appointment_time < ?))
                AND status != ?
                ORDER BY appointment_date DESC, appointment_time DESC 
                LIMIT 1
            ''', (phone_number, current_date, current_date, current_time, 'cancelled'))
            
            last_appointment = cursor.fetchone()
            last_date = last_appointment[0] if last_appointment else None
            
            # Update customer record
            cursor.execute('''
                UPDATE customers 
                SET total_appointments = ?, last_appointment_date = ?, updated_at = ?
                WHERE phone_number = ?
            ''', (total_count, last_date, datetime.now(self.timezone).isoformat(), phone_number))
            
            logger.debug(f"📊 Updated customer stats for {phone_number}: {total_count} appointments, last: {last_date}")
            
        except Exception as e:
            logger.error(f"❌ Error updating customer stats: {str(e)}")

    def refresh_all_customer_stats(self) -> bool:
        """Refresh statistics for all customers"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # Get all customer phone numbers
            cursor.execute('SELECT phone_number FROM customers')
            phone_numbers = [row[0] for row in cursor.fetchall()]
            
            # Update stats for each customer
            for phone_number in phone_numbers:
                self._update_customer_stats(cursor, phone_number)
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Refreshed stats for {len(phone_numbers)} customers")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error refreshing customer stats: {str(e)}")
            return False
    
    def create_or_update_customer_from_appointment(self, appointment_data: dict) -> bool:
        """Create or update customer when an appointment is booked"""
        try:
            phone_number = appointment_data.get('customer_phone')
            customer_name = appointment_data.get('customer_name')
            
            if not phone_number:
                return False
            
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # Check if customer exists
            cursor.execute('SELECT phone_number FROM customers WHERE phone_number = ?', (phone_number,))
            exists = cursor.fetchone() is not None
            
            now = datetime.now(self.timezone).isoformat()
            
            if exists:
                # Update existing customer
                cursor.execute('''
                    UPDATE customers 
                    SET name = COALESCE(name, ?), updated_at = ?
                    WHERE phone_number = ?
                ''', (customer_name, now, phone_number))
            else:
                # Create new customer
                cursor.execute('''
                    INSERT INTO customers (
                        phone_number, name, customer_since, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                ''', (phone_number, customer_name, now, now, now))
            
            # Update customer statistics
            self._update_customer_stats(cursor, phone_number)
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Customer {'updated' if exists else 'created'} from appointment: {phone_number}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error creating/updating customer from appointment: {str(e)}")
            return False

    # Message Templates Methods
    def get_all_message_templates(self) -> List[Dict]:
        """Get all message templates"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, template_type, title, description, message_content, 
                       is_enabled, max_chars, conditions, position, created_at, updated_at
                FROM message_templates
                ORDER BY template_type
            ''')
            
            rows = cursor.fetchall()
            conn.close()
            
            templates = []
            for row in rows:
                template = {
                    'id': row[0],
                    'template_type': row[1],
                    'title': row[2],
                    'description': row[3],
                    'message_content': row[4],
                    'is_enabled': bool(row[5]),
                    'max_chars': row[6],
                    'conditions': json.loads(row[7]) if row[7] else {},
                    'position': json.loads(row[8]) if row[8] else None,
                    'created_at': row[9],
                    'updated_at': row[10]
                }
                templates.append(template)
            
            return templates
            
        except Exception as e:
            logger.error(f"❌ Error getting message templates: {str(e)}")
            return []

    def get_message_template(self, template_type: str) -> Optional[Dict]:
        """Get a specific message template by type"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, template_type, title, description, message_content, 
                       is_enabled, max_chars, conditions, position, created_at, updated_at
                FROM message_templates
                WHERE template_type = ?
            ''', (template_type,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    'id': row[0],
                    'template_type': row[1],
                    'title': row[2],
                    'description': row[3],
                    'message_content': row[4],
                    'is_enabled': bool(row[5]),
                    'max_chars': row[6],
                    'conditions': json.loads(row[7]) if row[7] else {},
                    'position': json.loads(row[8]) if row[8] else None,
                    'created_at': row[9],
                    'updated_at': row[10]
                }
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting message template {template_type}: {str(e)}")
            return None

    def update_message_template(self, template_type: str, **kwargs) -> bool:
        """Update a message template - create if doesn't exist"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # First check if template exists
            cursor.execute('SELECT id FROM message_templates WHERE template_type = ?', (template_type,))
            template_exists = cursor.fetchone() is not None
            
            if not template_exists:
                # Create default template if it doesn't exist
                logger.info(f"📝 Creating missing template: {template_type}")
                default_templates = {
                    '24hr_reminder': {
                        'title': '24-Hour Reminder',
                        'description': None,
                        'message_content': "Hi {name}! Your {service} appointment is tomorrow at {time}. We're excited to see you! - Radiance MD Med Spa",
                        'is_enabled': True,
                        'max_chars': 160,
                        'conditions': {'hours_in_advance': 30, 'hours_before_appointment': 24}
                    },
                    'thank_you_review': {
                        'title': 'Thank You + Review',
                        'description': None,
                        'message_content': "Thanks for visiting Radiance MD Med Spa, {name}! We hope you loved your {service}! Leave us a review for 15% off your next visit: https://www.radiancemd.com/testimonials/ Code: REVIEW15",
                        'is_enabled': True,
                        'max_chars': 320,
                        'conditions': {'hours_after_appointment': 1}
                    },
                    'appointment_confirmation': {
                        'title': 'Appointment Confirmation',
                        'description': 'This is sent when the customer books an appointment',
                        'message_content': "Your {service} appointment with {specialist} is confirmed for {date} at {time}. Price: ${price}. Duration: {duration} minutes. See you then!",
                        'is_enabled': True,
                        'max_chars': 320,
                        'conditions': {}
                    },
                    'cancellation_confirmation': {
                        'title': 'Cancellation Confirmation',
                        'description': 'This is sent when a customer cancels their appointment',
                        'message_content': "Your {service} appointment on {date} at {time} has been cancelled. If you had a deposit, it will be refunded to your payment method. Please call us to reschedule if needed. Thank you!",
                        'is_enabled': True,
                        'max_chars': 320,
                        'conditions': {}
                    },
                    'refund_notification': {
                        'title': 'Refund Notification',
                        'description': 'This is sent when a customer shows up for their appointment and their deposit is refunded',
                        'message_content': "Great news! Your $50 show-up deposit has been refunded to your payment method. Thanks for keeping your appointment at Radiance MD Med Spa! 💫",
                        'is_enabled': True,
                        'max_chars': 160,
                        'conditions': {}
                    },
                    'missed_call_notification': {
                        'title': 'Missed Call Notification',
                        'description': 'This is sent to the caller if the front desk misses their call',
                        'message_content': "Hi! We missed your call to Radiance MD Med Spa. I'm here to help! How can I assist you today?",
                        'is_enabled': True,
                        'max_chars': 160,
                        'conditions': {}
                    }
                }
                
                if template_type in default_templates:
                    default = default_templates[template_type]
                    now = datetime.now(self.timezone).isoformat()
                    
                    cursor.execute('''
                        INSERT INTO message_templates 
                        (template_type, title, description, message_content, is_enabled, max_chars, conditions, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        template_type,
                        default['title'],
                        default['description'],
                        default['message_content'],
                        default['is_enabled'],
                        default['max_chars'],
                        json.dumps(default['conditions']),
                        now,
                        now
                    ))
                    conn.commit()
                    logger.info(f"✅ Created template: {template_type}")
                else:
                    logger.error(f"❌ Unknown template type: {template_type}")
                    conn.close()
                    return False
            
            # Now update the template
            update_fields = []
            values = []
            
            for key, value in kwargs.items():
                if key in ['title', 'description', 'message_content', 'is_enabled', 'max_chars']:
                    update_fields.append(f"{key} = ?")
                    values.append(value)
                elif key == 'conditions':
                    update_fields.append("conditions = ?")
                    values.append(json.dumps(value))
                elif key == 'position':
                    update_fields.append("position = ?")
                    values.append(json.dumps(value))
            
            if not update_fields:
                conn.close()
                return True  # No fields to update, consider it successful
            
            update_fields.append("updated_at = ?")
            values.append(datetime.now(self.timezone).isoformat())
            values.append(template_type)
            
            query = f'''
                UPDATE message_templates 
                SET {', '.join(update_fields)}
                WHERE template_type = ?
            '''
            
            cursor.execute(query, values)
            conn.commit()
            conn.close()
            
            success = cursor.rowcount > 0
            if success:
                logger.info(f"✅ Updated template: {template_type}")
            else:
                logger.warning(f"⚠️ No rows updated for template: {template_type}")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Error updating message template {template_type}: {str(e)}")
            return False

    def create_message_template(self, template_data: Dict) -> bool:
        """Create a new message template"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            now = datetime.now(self.timezone).isoformat()
            
            cursor.execute('''
                INSERT INTO message_templates 
                (template_type, title, description, message_content, is_enabled, max_chars, conditions, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                template_data['template_type'],
                template_data['title'],
                template_data.get('description'),
                template_data['message_content'],
                template_data.get('is_enabled', True),
                template_data.get('max_chars', 160),
                json.dumps(template_data.get('conditions', {})),
                now,
                now
            ))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"❌ Error creating message template: {str(e)}")
            return False

    def initialize_default_templates(self) -> bool:
        """Initialize default message templates if they don't exist"""
        try:
            default_templates = [
                {
                    'template_type': '24hr_reminder',
                    'title': '24-Hour Reminder',
                    'description': None,
                    'message_content': "Hi {name}! Your {service} appointment is tomorrow at {time}. We're excited to see you! - Radiance MD Med Spa",
                    'is_enabled': True,
                    'max_chars': 160,
                    'conditions': {
                        'hours_in_advance': 30,
                        'hours_before_appointment': 24
                    }
                },
                {
                    'template_type': 'thank_you_review',
                    'title': 'Thank You + Review',
                    'description': None,
                    'message_content': "Thanks for visiting Radiance MD Med Spa, {name}! We hope you loved your {service}! Leave us a review for 15% off your next visit: https://www.radiancemd.com/testimonials/ Code: REVIEW15",
                    'is_enabled': True,
                    'max_chars': 320,
                    'conditions': {
                        'hours_after_appointment': 1
                    }
                },
                {
                    'template_type': 'appointment_confirmation',
                    'title': 'Appointment Confirmation',
                    'description': 'This is sent when the customer books an appointment',
                    'message_content': "Your {service} appointment with {specialist} is confirmed for {date} at {time}. Price: ${price}. Duration: {duration} minutes. See you then!",
                    'is_enabled': True,
                    'max_chars': 320,
                    'conditions': {}
                },
                {
                    'template_type': 'cancellation_confirmation',
                    'title': 'Cancellation Confirmation',
                    'description': 'This is sent when a customer cancels their appointment',
                    'message_content': "Your {service} appointment on {date} at {time} has been cancelled. If you had a deposit, it will be refunded to your payment method. Please call us to reschedule if needed. Thank you!",
                    'is_enabled': True,
                    'max_chars': 320,
                    'conditions': {}
                },
                {
                    'template_type': 'refund_notification',
                    'title': 'Refund Notification',
                    'description': 'This is sent when a customer shows up for their appointment and their deposit is refunded',
                    'message_content': "Great news! Your $50 show-up deposit has been refunded to your payment method. Thanks for keeping your appointment at Radiance MD Med Spa! 💫",
                    'is_enabled': True,
                    'max_chars': 160,
                    'conditions': {}
                },
                {
                    'template_type': 'missed_call_notification',
                    'title': 'Missed Call Notification',
                    'description': 'This is sent to the caller if the front desk misses their call',
                    'message_content': "Hi! We missed your call to Radiance MD Med Spa. I'm here to help! How can I assist you today?",
                    'is_enabled': True,
                    'max_chars': 160,
                    'conditions': {}
                }
            ]
            
            for template in default_templates:
                if not self.get_message_template(template['template_type']):
                    self.create_message_template(template)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error initializing default templates: {str(e)}")
            return False
    
    def restore_default_templates(self) -> bool:
        """Restore message templates to their original default values"""
        try:
            # Update each template with default values
            self.update_message_template('24hr_reminder',
                title='24-Hour Reminder',
                description=None,
                message_content="Hi {name}! Your {service} appointment is tomorrow at {time}. We're excited to see you! - Radiance MD Med Spa",
                is_enabled=True,
                max_chars=160,
                conditions={'hours_in_advance': 30, 'hours_before_appointment': 24}
            )
            
            self.update_message_template('thank_you_review',
                title='Thank You + Review',
                description=None,
                message_content="Thanks for visiting Radiance MD Med Spa, {name}! We hope you loved your {service}! Leave us a review for 15% off your next visit: https://www.radiancemd.com/testimonials/ Code: REVIEW15",
                is_enabled=True,
                max_chars=320,
                conditions={'hours_after_appointment': 1}
            )
            
            self.update_message_template('appointment_confirmation',
                title='Appointment Confirmation',
                description='This is sent when the customer books an appointment',
                message_content="Your {service} appointment with {specialist} is confirmed for {date} at {time}. Price: ${price}. Duration: {duration} minutes. See you then!",
                is_enabled=True,
                max_chars=160,
                conditions={}
            )
            
            self.update_message_template('cancellation_confirmation',
                title='Cancellation Confirmation',
                description='This is sent when a customer cancels their appointment',
                message_content="Your {service} appointment on {date} at {time} has been cancelled. If you had a deposit, it will be refunded to your payment method. Please call us to reschedule if needed. Thank you!",
                is_enabled=True,
                max_chars=320,
                conditions={}
            )
            
            self.update_message_template('refund_notification',
                title='Refund Notification',
                description='This is sent when a customer shows up for their appointment and their deposit is refunded',
                message_content="Great news! Your $50 show-up deposit has been refunded to your payment method. Thanks for keeping your appointment at Radiance MD Med Spa!",
                is_enabled=True,
                max_chars=160,
                conditions={}
            )
            
            self.update_message_template('missed_call_notification',
                title='Missed Call Notification',
                description='This is sent to the caller if the front desk misses their call',
                message_content="Hi! We missed your call to Radiance MD Med Spa. I'm here to help! How can I assist you today?",
                is_enabled=True,
                max_chars=160,
                conditions={}
            )
            
            logger.info("✅ Default templates restored successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error restoring default templates: {str(e)}")
            return False

   
