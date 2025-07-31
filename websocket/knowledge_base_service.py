import os
import json
import logging
import requests
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import sqlite3
import openai
from bs4 import BeautifulSoup
import PyPDF2
import docx
import io
import re
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

class KnowledgeBaseService:
    """Service for processing and retrieving knowledge base information"""
    
    def __init__(self, database_service=None):
        self.db = database_service
        
        # FIXED: Better OpenAI client initialization with error handling
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.error("❌ OPENAI_API_KEY not found in environment variables")
            logger.error("❌ Please check your .env file contains: OPENAI_API_KEY=your_key_here")
            raise ValueError("OPENAI_API_KEY environment variable is required")
        
        try:
            self.openai_client = openai.OpenAI(api_key=api_key)
            logger.info("✅ OpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize OpenAI client: {str(e)}")
            raise
        
        # Hardcoded trigger keywords for reliable function calling
        self.trigger_keywords = {
            'hours': [
                'hours', 'open', 'close', 'closed', 'when', 'time', 'schedule',
                'available', 'operating', 'business hours', 'what time'
            ],
            'services': [
                'services', 'treatment', 'procedure', 'botox', 'filler', 'facial',
                'laser', 'microneedling', 'chemical peel', 'what do you do',
                'what services', 'treatments available', 'procedures'
            ],
            'location': [
                'address', 'location', 'where', 'directions', 'find you',
                'located', 'address', 'street', 'building'
            ],
            'staff': [
                'doctor', 'staff', 'specialist', 'who', 'practitioner',
                'provider', 'team', 'employees', 'workers'
            ],
            'pricing': [
                'cost', 'price', 'expensive', 'cheap', 'fee', 'charge',
                'how much', 'pricing', 'rates', 'payment'
            ],
            'policies': [
                'policy', 'cancellation', 'reschedule', 'deposit', 'refund',
                'insurance', 'payment', 'booking', 'appointment policy'
            ]
        }
        
        # Initialize knowledge base database tables
        self._init_knowledge_base_tables()
    
    def _init_knowledge_base_tables(self):
        """Initialize knowledge base specific tables"""
        if not self.db:
            return
            
        try:
            conn = sqlite3.connect(self.db.db_file)
            cursor = conn.cursor()
            
            # Knowledge base content table (for processed content)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS kb_content (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id INTEGER NOT NULL,
                    content_type TEXT NOT NULL,  -- 'chunk', 'section', 'full'
                    title TEXT,
                    content TEXT NOT NULL,
                    embedding TEXT,  -- JSON string of embedding vector
                    keywords TEXT,   -- JSON string of extracted keywords
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (source_id) REFERENCES knowledge_base (id)
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info("✅ Knowledge base tables initialized")
            
        except Exception as e:
            logger.error(f"❌ Error initializing knowledge base tables: {str(e)}")
    
    def should_trigger_knowledge_function(self, user_message: str) -> Tuple[bool, Optional[str]]:
        """
        Determine if knowledge base function should be triggered using hybrid approach
        
        Returns:
            Tuple of (should_trigger, query_type)
        """
        message_lower = user_message.lower()
        
        # First check for trigger keywords (hardcoded reliability)
        for query_type, keywords in self.trigger_keywords.items():
            for keyword in keywords:
                if keyword in message_lower:
                    logger.info(f"🎯 Trigger keyword '{keyword}' found for query_type: {query_type}")
                    return True, query_type
        
        # If no trigger keywords found, let AI decide (but this is secondary)
        # We'll implement this as a simple heuristic for now
        business_question_indicators = [
            '?', 'what', 'when', 'where', 'how', 'who', 'can you tell me',
            'do you', 'are you', 'is there', 'information about'
        ]
        
        has_question_indicator = any(indicator in message_lower for indicator in business_question_indicators)
        
        if has_question_indicator:
            logger.info(f"🤔 Question indicator found, triggering knowledge function with 'general' type")
            return True, 'general'
        
        return False, None
    
    def process_document(self, file_path: str, item_id: int, file_type: str) -> bool:
        """Process uploaded document and extract content"""
        try:
            logger.info(f"📄 Processing document: {file_path} (type: {file_type})")
            
            content = ""
            
            if file_type.lower() == 'pdf':
                content = self._extract_pdf_content(file_path)
            elif file_type.lower() in ['doc', 'docx']:
                content = self._extract_docx_content(file_path)
            elif file_type.lower() == 'txt':
                content = self._extract_txt_content(file_path)
            else:
                logger.error(f"❌ Unsupported file type: {file_type}")
                return False
            
            if not content.strip():
                logger.warning(f"⚠️ No content extracted from {file_path}")
                return False
            
            # Process and store content
            return self._process_and_store_content(item_id, content, f"Document: {os.path.basename(file_path)}")
            
        except Exception as e:
            logger.error(f"❌ Error processing document {file_path}: {str(e)}")
            return False
    
    def process_link(self, url: str, item_id: int) -> bool:
        """Process URL and extract content"""
        try:
            logger.info(f"🔗 Processing link: {url}")
            
            # Fetch webpage content
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # Parse with BeautifulSoup
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Extract text content
            content = soup.get_text()
            
            # Clean up content
            content = self._clean_text_content(content)
            
            if not content.strip():
                logger.warning(f"⚠️ No content extracted from {url}")
                return False
            
            # NEW: Clean and structure content with GPT
            cleaned_markdown = self.clean_and_structure_content_with_gpt(content)
            if cleaned_markdown and cleaned_markdown.strip():
                logger.info("✨ Using GPT-cleaned structured markdown for chunking and storage")
                content_to_store = cleaned_markdown
                title = f"Website (Cleaned): {url}"
            else:
                logger.warning("⚠️ GPT cleaning failed or returned empty. Using fallback cleaned text.")
                content_to_store = content
                title = f"Website: {url}"
            
            # Process and store content
            return self._process_and_store_content(item_id, content_to_store, title)
            
        except Exception as e:
            logger.error(f"❌ Error processing link {url}: {str(e)}")
            return False
    
    def _extract_pdf_content(self, file_path: str) -> str:
        """Extract text from PDF file"""
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                content = ""
                for page in pdf_reader.pages:
                    content += page.extract_text() + "\n"
                return content
        except Exception as e:
            logger.error(f"❌ Error extracting PDF content: {str(e)}")
            return ""
    
    def _extract_docx_content(self, file_path: str) -> str:
        """Extract text from DOCX file"""
        try:
            doc = docx.Document(file_path)
            content = ""
            for paragraph in doc.paragraphs:
                content += paragraph.text + "\n"
            return content
        except Exception as e:
            logger.error(f"❌ Error extracting DOCX content: {str(e)}")
            return ""
    
    def _extract_txt_content(self, file_path: str) -> str:
        """Extract text from TXT file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except Exception as e:
            logger.error(f"❌ Error extracting TXT content: {str(e)}")
            return ""
    
    def _clean_text_content(self, content: str) -> str:
        """Clean and normalize text content"""
        # Remove excessive whitespace
        content = re.sub(r'\s+', ' ', content)
        
        # Remove empty lines
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        
        return '\n'.join(lines)
    
    def _process_and_store_content(self, source_id: int, content: str, title: str) -> bool:
        """Process content into chunks and store with embeddings"""
        try:
            # Split content into manageable chunks
            chunks = self._chunk_content(content)
            
            conn = sqlite3.connect(self.db.db_file)
            cursor = conn.cursor()
            
            for i, chunk in enumerate(chunks):
                # Generate embedding for chunk
                embedding = self._generate_embedding(chunk)
                
                # Extract keywords
                keywords = self._extract_keywords(chunk)
                
                # Store chunk
                cursor.execute('''
                    INSERT INTO kb_content 
                    (source_id, content_type, title, content, embedding, keywords, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    source_id,
                    'chunk',
                    f"{title} - Part {i+1}",
                    chunk,
                    json.dumps(embedding) if embedding else None,
                    json.dumps(keywords),
                    datetime.now().isoformat()
                ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Processed and stored {len(chunks)} chunks for source {source_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error processing and storing content: {str(e)}")
            return False
    
    def _chunk_content(self, content: str, max_chunk_size: int = 1000) -> List[str]:
        """Split content into chunks for processing"""
        # Simple chunking by sentences/paragraphs
        paragraphs = content.split('\n\n')
        chunks = []
        current_chunk = ""
        
        for paragraph in paragraphs:
            if len(current_chunk) + len(paragraph) <= max_chunk_size:
                current_chunk += paragraph + "\n\n"
            else:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = paragraph + "\n\n"
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for text using OpenAI"""
        try:
            response = self.openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"❌ Error generating embedding: {str(e)}")
            return None
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text with improved relevance"""
        # Enhanced keyword extraction that preserves important question words
        words = re.findall(r'\b[a-zA-Z]{2,}\b', text.lower())
        
        # Reduced stop words - keep important question and context words
        stop_words = {
            'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 
            'her', 'was', 'one', 'our', 'out', 'get', 'has', 'him', 'his', 
            'how', 'its', 'may', 'new', 'now', 'old', 'see', 'two', 'boy', 
            'did', 'she', 'use', 'way', 'will', 'with', 'this', 'that', 'they',
            'have', 'been', 'from', 'each', 'which', 'their', 'time', 'would',
            'there', 'could', 'other', 'than', 'first', 'water', 'been', 'call',
            'who', 'oil', 'sit', 'now', 'find', 'down', 'day', 'did', 'get',
            'come', 'made', 'may', 'part', 'over', 'new', 'sound', 'take',
            'only', 'little', 'work', 'know', 'place', 'year', 'live', 'me',
            'back', 'give', 'most', 'very', 'after', 'thing', 'our', 'just',
            'name', 'good', 'sentence', 'man', 'think', 'say', 'great', 'where',
            'help', 'through', 'much', 'before', 'line', 'right', 'too', 'mean',
            'old', 'any', 'same', 'tell', 'boy', 'follow', 'came', 'want',
            'show', 'also', 'around', 'form', 'three', 'small', 'set', 'put',
            'end', 'does', 'another', 'well', 'large', 'must', 'big', 'even',
            'such', 'because', 'turn', 'here', 'why', 'ask', 'went', 'men',
            'read', 'need', 'land', 'different', 'home', 'us', 'move', 'try',
            'kind', 'hand', 'picture', 'again', 'change', 'off', 'play', 'spell',
            'air', 'away', 'animal', 'house', 'point', 'page', 'letter', 'mother',
            'answer', 'found', 'study', 'still', 'learn', 'should', 'America',
            'world', 'high', 'every', 'near', 'add', 'food', 'between', 'own',
            'below', 'country', 'plant', 'last', 'school', 'father', 'keep',
            'tree', 'never', 'start', 'city', 'earth', 'eye', 'light', 'thought',
            'head', 'under', 'story', 'saw', 'left', 'don', 'few', 'while',
            'along', 'might', 'close', 'something', 'seem', 'next', 'hard',
            'open', 'example', 'begin', 'life', 'always', 'those', 'both',
            'paper', 'together', 'got', 'group', 'often', 'run', 'important',
            'until', 'children', 'side', 'feet', 'car', 'mile', 'night', 'walk',
            'white', 'sea', 'began', 'grow', 'took', 'river', 'four', 'carry',
            'state', 'once', 'book', 'hear', 'stop', 'without', 'second',
            'late', 'miss', 'idea', 'enough', 'eat', 'face', 'watch', 'far',
            'Indian', 'real', 'almost', 'let', 'above', 'girl', 'sometimes',
            'mountain', 'cut', 'young', 'talk', 'soon', 'list', 'song', 'being',
            'leave', 'family', 'it', 'body', 'music', 'color', 'stand', 'sun',
            'questions', 'fish', 'area', 'mark', 'dog', 'horse', 'birds',
            'problem', 'complete', 'room', 'knew', 'since', 'ever', 'piece',
            'told', 'usually', 'didn', 'friends', 'easy', 'heard', 'order',
            'red', 'door', 'sure', 'become', 'top', 'ship', 'across', 'today',
            'during', 'short', 'better', 'best', 'however', 'low', 'hours',
            'black', 'products', 'happened', 'whole', 'measure', 'remember',
            'early', 'waves', 'reached', 'listen', 'wind', 'rock', 'space',
            'covered', 'fast', 'several', 'hold', 'himself', 'toward', 'five',
            'step', 'morning', 'passed', 'vowel', 'true', 'hundred', 'against',
            'pattern', 'numeral', 'table', 'north', 'slowly', 'money', 'map',
            'farm', 'pulled', 'draw', 'voice', 'seen', 'cold', 'cried', 'plan',
            'notice', 'south', 'sing', 'war', 'ground', 'fall', 'king', 'town',
            'I', 'unit', 'figure', 'certain', 'field', 'travel', 'wood',
            'fire', 'upon', 'done', 'English', 'road', 'half', 'ten', 'fly',
            'gave', 'box', 'finally', 'wait', 'correct', 'oh', 'quickly',
            'person', 'became', 'shown', 'minutes', 'strong', 'verb', 'stars',
            'front', 'feel', 'fact', 'inches', 'street', 'decided', 'contain',
            'course', 'surface', 'produce', 'building', 'ocean', 'class',
            'note', 'nothing', 'rest', 'carefully', 'scientists', 'inside',
            'wheels', 'stay', 'green', 'known', 'island', 'week', 'less',
            'machine', 'base', 'ago', 'stood', 'plane', 'system', 'behind',
            'ran', 'round', 'boat', 'game', 'force', 'brought', 'understand',
            'warm', 'common', 'bring', 'explain', 'dry', 'though', 'language',
            'shape', 'deep', 'thousands', 'yes', 'clear', 'equation', 'yet',
            'government', 'filled', 'heat', 'full', 'hot', 'check', 'object',
            'am', 'rule', 'among', 'noun', 'power', 'cannot', 'able', 'six',
            'size', 'dark', 'ball', 'material', 'special', 'heavy', 'fine',
            'pair', 'circle', 'include', 'built', 'can', 'matter', 'square',
            'syllables', 'perhaps', 'bill', 'felt', 'suddenly', 'test',
            'direction', 'center', 'farmers', 'ready', 'anything', 'divided',
            'general', 'energy', 'subject', 'Europe', 'moon', 'region', 'return',
            'believe', 'dance', 'members', 'picked', 'simple', 'cells', 'paint',
            'mind', 'love', 'cause', 'rain', 'exercise', 'eggs', 'train',
            'blue', 'wish', 'drop', 'developed', 'window', 'difference',
            'distance', 'heart', 'site', 'sum', 'summer', 'wall', 'forest',
            'probably', 'legs', 'sat', 'main', 'winter', 'wide', 'written',
            'length', 'reason', 'kept', 'interest', 'arms', 'brother', 'race',
            'present', 'beautiful', 'store', 'job', 'edge', 'past', 'sign',
            'record', 'finished', 'discovered', 'wild', 'happy', 'beside',
            'gone', 'sky', 'grass', 'million', 'west', 'lay', 'weather',
            'root', 'instruments', 'meet', 'third', 'months', 'paragraph',
            'raised', 'represent', 'soft', 'whether', 'clothes', 'flowers',
            'shall', 'teacher', 'held', 'describe', 'drive', 'cross',
            'speak', 'solve', 'appear', 'metal', 'son', 'either', 'ice',
            'sleep', 'village', 'factors', 'result', 'jumped', 'snow',
            'ride', 'care', 'floor', 'hill', 'pushed', 'baby', 'buy',
            'century', 'outside', 'everything', 'tall', 'already', 'instead',
            'phrase', 'soil', 'bed', 'copy', 'free', 'hope', 'spring',
            'case', 'laughed', 'nation', 'quite', 'type', 'themselves',
            'bright', 'lead', 'everyone', 'moment', 'scale', 'basic',
            'happen', 'bear', 'fine', 'someone', 'direction', 'spring',
            'nation', 'quite', 'type', 'themselves', 'bright', 'lead',
            'everyone', 'moment', 'scale', 'basic', 'happen', 'bear',
            'fine', 'someone', 'direction', 'spring', 'nation', 'quite',
            'type', 'themselves', 'bright', 'lead', 'everyone', 'moment',
            'scale', 'basic', 'happen', 'bear', 'fine', 'someone'
        }
        
        # Keep important question words and context words
        important_words = {
            'who', 'what', 'when', 'where', 'why', 'how', 'which', 'whose',
            'main', 'primary', 'chief', 'head', 'director', 'manager',
            'cost', 'price', 'fee', 'charge', 'expensive', 'cheap',
            'hours', 'time', 'schedule', 'open', 'closed', 'available',
            'location', 'address', 'where', 'directions', 'find',
            'services', 'treatments', 'procedures', 'offer', 'provide',
            'staff', 'team', 'doctor', 'specialist', 'practitioner',
            'policies', 'rules', 'cancellation', 'deposit', 'refund'
        }
        
        # Filter words but keep important ones
        keywords = []
        for word in set(words):
            if word not in stop_words or word in important_words:
                keywords.append(word)
        
        return keywords[:25]  # Increased limit for better coverage
    
    def search_knowledge_base(self, query: str, query_type: str = 'general') -> str:
        """Search knowledge base and return relevant information with improved matching"""
        try:
            logger.info(f"🔍 Searching knowledge base for: '{query}' (type: {query_type})")
            
            if not self.db:
                return "Knowledge base not available."
            
            # Enhanced search with query type specific handling
            results = self._enhanced_search(query, query_type)
            
            # Always check staff management for staff queries, even if no results
            if query_type == 'staff':
                return self._format_staff_results(results)
            
            if results:
                logger.info(f"✅ Found {len(results)} relevant matches")
                return self._format_search_results(results, query_type)
            
            logger.info("❌ No relevant information found in knowledge base")
            return "I don't have specific information about that in our knowledge base."
            
        except Exception as e:
            logger.error(f"❌ Error searching knowledge base: {str(e)}")
            return "I'm having trouble accessing our knowledge base right now. Please try again."
    
    def _enhanced_search(self, query: str, query_type: str) -> List[Dict]:
        """Enhanced search with query type specific handling"""
        try:
            conn = sqlite3.connect(self.db.db_file)
            cursor = conn.cursor()
            
            # Get all content for comprehensive search
            cursor.execute('''
                SELECT kc.content, kc.title, kc.keywords, kc.embedding
                FROM kb_content kc
            ''')
            
            all_content = cursor.fetchall()
            conn.close()
            
            if not all_content:
                return []
            
            # Query type specific search patterns
            search_patterns = self._get_search_patterns(query, query_type)
            
            # Score and rank results
            scored_results = []
            for row in all_content:
                content, title, keywords, embedding = row
                score = self._calculate_relevance_score(content, title, keywords, query, query_type, search_patterns)
                
                if score > 0.1:  # Minimum relevance threshold
                    scored_results.append({
                        'content': content,
                        'title': title,
                        'keywords': keywords,
                        'score': score,
                        'relevance': 'enhanced'
                    })
            
            # Sort by score and return top results
            scored_results.sort(key=lambda x: x['score'], reverse=True)
            return scored_results[:5]  # Return top 5 results
            
        except Exception as e:
            logger.error(f"❌ Error in enhanced search: {str(e)}")
            return []
    
    def _get_search_patterns(self, query: str, query_type: str) -> List[str]:
        """Get search patterns based on query type"""
        query_lower = query.lower()
        patterns = []
        
        # Add original query keywords
        query_keywords = self._extract_keywords(query)
        patterns.extend(query_keywords)
        
        # Add query type specific patterns
        if query_type == 'staff':
            patterns.extend(['doctor', 'medical director', 'specialist', 'practitioner', 'staff', 'team'])
            if 'main' in query_lower or 'primary' in query_lower or 'head' in query_lower:
                patterns.extend(['medical director', 'chief', 'head', 'main', 'primary'])
        elif query_type == 'services':
            patterns.extend(['services', 'treatments', 'procedures', 'offer', 'provide', 'available'])
        elif query_type == 'pricing':
            patterns.extend(['cost', 'price', 'fee', 'charge', 'rates', 'pricing'])
        elif query_type == 'location':
            patterns.extend(['address', 'location', 'where', 'directions', 'find'])
        elif query_type == 'hours':
            patterns.extend(['hours', 'time', 'schedule', 'open', 'closed', 'available'])
        elif query_type == 'policies':
            patterns.extend(['policy', 'policies', 'rules', 'cancellation', 'deposit', 'refund'])
        
        return list(set(patterns))  # Remove duplicates
    
    def _calculate_relevance_score(self, content: str, title: str, keywords: str, query: str, query_type: str, search_patterns: List[str]) -> float:
        """Calculate relevance score for content"""
        content_lower = content.lower()
        title_lower = title.lower()
        
        score = 0.0
        
        # Exact phrase matching (highest weight)
        for pattern in search_patterns:
            if pattern in content_lower:
                score += 10.0
            if pattern in title_lower:
                score += 15.0  # Title matches are more important
        
        # Query type specific scoring
        if query_type == 'staff':
            # Boost staff-related content
            staff_indicators = ['dr.', 'doctor', 'medical director', 'specialist', 'practitioner']
            for indicator in staff_indicators:
                if indicator in content_lower:
                    score += 5.0
            
            # Special handling for "main doctor" queries
            if 'main' in query.lower() or 'primary' in query.lower():
                if 'medical director' in content_lower:
                    score += 20.0  # High boost for medical director
                if 'chief' in content_lower or 'head' in content_lower:
                    score += 15.0
        
        elif query_type == 'services':
            # Boost service-related content
            service_indicators = ['services', 'treatments', 'procedures', 'offer', 'provide']
            for indicator in service_indicators:
                if indicator in content_lower:
                    score += 3.0
        
        elif query_type == 'pricing':
            # Boost pricing-related content
            pricing_indicators = ['$', 'cost', 'price', 'fee', 'charge', 'rates']
            for indicator in pricing_indicators:
                if indicator in content_lower:
                    score += 5.0
        
        elif query_type == 'location':
            # Boost location-related content
            location_indicators = ['address', 'location', 'street', 'road', 'michigan', 'canton']
            for indicator in location_indicators:
                if indicator in content_lower:
                    score += 5.0
        
        elif query_type == 'hours':
            # Boost hours-related content
            hours_indicators = ['hours', 'am', 'pm', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            for indicator in hours_indicators:
                if indicator in content_lower:
                    score += 3.0
        
        # Keyword density scoring
        query_words = set(query.lower().split())
        content_words = set(content_lower.split())
        word_overlap = len(query_words.intersection(content_words))
        score += word_overlap * 2.0
        
        # Length penalty (prefer concise, relevant content)
        if len(content) > 500:
            score *= 0.8
        
        return score
    
    def _format_search_results(self, results: List[Dict], query_type: str) -> str:
        """Format search results into a coherent response with query type optimization"""
        if not results:
            return "I don't have specific information about that."
        
        # Sort by score for best results first
        results.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        # Query type specific formatting
        if query_type == 'staff':
            return self._format_staff_results(results)
        elif query_type == 'services':
            return self._format_services_results(results)
        elif query_type == 'pricing':
            return self._format_pricing_results(results)
        elif query_type == 'location':
            return self._format_location_results(results)
        elif query_type == 'hours':
            return self._format_hours_results(results)
        elif query_type == 'policies':
            return self._format_policies_results(results)
        else:
            return self._format_general_results(results)
    
    def _format_staff_results(self, results: List[Dict]) -> str:
        """Hybrid: Combine staff management and knowledge base info for staff queries."""
        # Get staff management list
        staff_names = self.db.get_active_staff_names() if self.db else []
        staff_list_str = self._format_staff_management_results(staff_names) if staff_names else None

        # Extract specific information from knowledge base results
        kb_personal_info = []
        for result in results[:3]:
            content = result['content']

            # Look for medical director information
            if 'medical director:' in content.lower():
                # Find the medical director section
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if 'medical director:' in line.lower():
                        # Get the medical director line and the next line (description)
                        medical_director_line = line.strip()
                        if i + 1 < len(lines) and lines[i + 1].strip():
                            description_line = lines[i + 1].strip()
                            kb_personal_info.append(f"{medical_director_line}\n{description_line}")
                        else:
                            kb_personal_info.append(medical_director_line)
                        break

            # Look for specific staff names in the content (but skip if we already found medical director info)
            if not any('medical director:' in info.lower() for info in kb_personal_info):
                for name in staff_names:
                    if name.lower() in content.lower():
                        # Find the line containing the staff name
                        lines = content.split('\n')
                        for i, line in enumerate(lines):
                            if name.lower() in line.lower():
                                # Get the line with the name and potentially the next line
                                name_line = line.strip()
                                if i + 1 < len(lines) and lines[i + 1].strip() and not any(skip_word in lines[i + 1].lower() for skip_word in ['policies:', 'contact:', 'phone:', 'website:', 'hours:', 'location:']):
                                    next_line = lines[i + 1].strip()
                                    kb_personal_info.append(f"{name_line}\n{next_line}")
                                else:
                                    kb_personal_info.append(name_line)
                                break

        # Remove duplicates
        kb_personal_info = list(dict.fromkeys(kb_personal_info))

        # Combine staff list with knowledge base information
        if kb_personal_info and staff_list_str:
            return f"{staff_list_str}\n\n" + '\n\n'.join(kb_personal_info)
        elif kb_personal_info:
            return '\n\n'.join(kb_personal_info)
        elif staff_list_str:
            return staff_list_str
        else:
            return self._format_general_results(results)
    
    def _format_staff_management_results(self, staff_names: List[str]) -> str:
        """Format staff information from staff management settings"""
        if not staff_names:
            return "Our staff will be assigned based on availability."
        
        # Get full staff information including positions
        staff_info = self.db.get_all_staff(include_inactive=False) if self.db else []
        
        if not staff_info:
            # Fallback to just names if we can't get full info
            if len(staff_names) == 1:
                return f"Our specialist is {staff_names[0]}."
            elif len(staff_names) == 2:
                return f"Our specialists are {staff_names[0]} and {staff_names[1]}."
            else:
                staff_list = ', '.join(staff_names[:-1]) + f" and {staff_names[-1]}"
                return f"Our specialists are {staff_list}."
        
        # Format with positions
        active_staff = [s for s in staff_info if s.get('active', True)]
        
        if len(active_staff) == 1:
            staff = active_staff[0]
            position = staff.get('position', 'Specialist')
            return f"Our {position.lower()} is {staff['name']}."
        elif len(active_staff) == 2:
            staff1, staff2 = active_staff[0], active_staff[1]
            pos1 = staff1.get('position', 'Specialist').lower()
            pos2 = staff2.get('position', 'Specialist').lower()
            return f"Our {pos1} is {staff1['name']} and our {pos2} is {staff2['name']}."
        else:
            # For multiple staff, group by position
            staff_by_position = {}
            for s in active_staff:
                position = s.get('position', 'Specialist')
                if position not in staff_by_position:
                    staff_by_position[position] = []
                staff_by_position[position].append(s['name'])
            
            position_descriptions = []
            for position, names in staff_by_position.items():
                if len(names) == 1:
                    position_descriptions.append(f"{position}: {names[0]}")
                else:
                    name_list = ', '.join(names[:-1]) + f" and {names[-1]}"
                    position_descriptions.append(f"{position}s: {name_list}")
            
            return "Our staff includes " + "; ".join(position_descriptions) + "."
    
    def _format_services_results(self, results: List[Dict]) -> str:
        """Format services-related results"""
        services_info = []
        for result in results[:3]:
            content = result['content']
            # Look for services section
            if 'services' in content.lower() or 'treatments' in content.lower():
                lines = content.split('\n')
                for line in lines:
                    if any(word in line.lower() for word in ['botox', 'filler', 'facial', 'laser', 'peel', 'microneedling']):
                        services_info.append(line.strip())
        
        if services_info:
            return '\n'.join(services_info[:8])  # Limit to 8 lines
        else:
            return self._format_general_results(results)
    
    def _format_pricing_results(self, results: List[Dict]) -> str:
        """Format pricing-related results"""
        pricing_info = []
        for result in results[:3]:
            content = result['content']
            # Look for pricing information
            if '$' in content or 'cost' in content.lower() or 'price' in content.lower():
                lines = content.split('\n')
                for line in lines:
                    if '$' in line or 'cost' in line.lower() or 'price' in line.lower():
                        pricing_info.append(line.strip())
        
        if pricing_info:
            return '\n'.join(pricing_info[:6])  # Limit to 6 lines
        else:
            return self._format_general_results(results)
    
    def _format_location_results(self, results: List[Dict]) -> str:
        """Format location-related results"""
        location_info = []
        for result in results[:2]:  # Top 2 results
            content = result['content']
            # Look for address information
            if 'address' in content.lower() or 'location' in content.lower() or 'canton' in content.lower():
                lines = content.split('\n')
                for line in lines:
                    if any(word in line.lower() for word in ['address', 'location', 'canton', 'michigan', 'road', 'street']):
                        location_info.append(line.strip())
        
        if location_info:
            return '\n'.join(location_info[:3])  # Limit to 3 lines
        else:
            return self._format_general_results(results)
    
    def _format_hours_results(self, results: List[Dict]) -> str:
        """Format hours-related results"""
        hours_info = []
        for result in results[:2]:
            content = result['content']
            # Look for hours information
            if 'hours' in content.lower() or 'am' in content.lower() or 'pm' in content.lower():
                lines = content.split('\n')
                for line in lines:
                    if any(word in line.lower() for word in ['hours', 'am', 'pm', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']):
                        hours_info.append(line.strip())
        
        if hours_info:
            return '\n'.join(hours_info[:5])  # Limit to 5 lines
        else:
            return self._format_general_results(results)
    
    def _format_policies_results(self, results: List[Dict]) -> str:
        """Format policies-related results"""
        policies_info = []
        for result in results[:3]:
            content = result['content']
            # Look for policy information
            if 'policy' in content.lower() or 'deposit' in content.lower() or 'cancellation' in content.lower():
                lines = content.split('\n')
                for line in lines:
                    if any(word in line.lower() for word in ['policy', 'deposit', 'cancellation', 'refund', 'payment']):
                        policies_info.append(line.strip())
        
        if policies_info:
            return '\n'.join(policies_info[:6])  # Limit to 6 lines
        else:
            return self._format_general_results(results)
    
    def _format_general_results(self, results: List[Dict]) -> str:
        """Format general results"""
        # Combine relevant content with better selection
        combined_content = ""
        for result in results[:3]:  # Top 3 results
            content = result['content']
            # Limit each chunk to avoid overwhelming the AI
            if len(content) > 300:
                content = content[:300] + "..."
            combined_content += content + "\n\n"
        
        # Trim to reasonable length
        if len(combined_content) > 800:
            combined_content = combined_content[:800] + "..."
        
        return combined_content.strip()
    
    def clean_and_structure_content_with_gpt(self, raw_text: str) -> Optional[str]:
        """Clean and organize raw website text into structured markdown using GPT."""
        try:
            prompt = (
                "You are an expert at organizing and cleaning website content for use in an AI knowledge base.\n"
                "Given the following raw website text, do the following:\n"
                "1. Remove all navigation menus, repeated information, and irrelevant content (such as footers, accessibility tools, and validation fields).\n"
                "2. Deduplicate any repeated information (such as phone numbers, addresses, or calls to action).\n"
                "3. Organize the remaining information into clear, logical sections using markdown headers (e.g., ## About, ## Services, ## Testimonials, ## Office Hours, ## Contact, ## Policies, ## Other Important Info).\n"
                "4. If you find information that doesn't fit a main section, place it under '## Other Important Info'.\n"
                "5. Make sure each section is concise, readable, and only contains relevant information for a potential client or receptionist AI.\n"
                "6. Do not include any instructions or explanations—just output the cleaned, organized markdown.\n\n"
                "**Important: Only output the cleaned, organized markdown content. Do not include any notes, explanations, or meta-comments. Do not say what you did—just output the sorted information.**\n\n"
                "Here is the raw website text:\n"
                f"""\n{raw_text}\n"""
            )
            response = self.openai_client.chat.completions.create(
                model="gpt-4.1-nano",  # Use the budget model for cost efficiency
                messages=[
                    {"role": "system", "content": "You are an expert at cleaning and organizing website content for AI knowledge bases."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=2048
            )
            cleaned_markdown = response.choices[0].message.content.strip()
            logger.info("✅ Cleaned and structured content with GPT")
            return cleaned_markdown
        except Exception as e:
            logger.error(f"❌ Error cleaning and structuring content with GPT: {str(e)}")
            return None
    
    def extract_internal_links_and_titles(self, base_url: str, max_pages: int = 30) -> list:
        """Extract all internal links and their titles from the given base URL."""
        try:
            # Ensure base_url has a scheme
            if not base_url.lower().startswith(('http://', 'https://')):
                base_url = 'https://' + base_url
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(base_url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            base_domain = urlparse(base_url).netloc
            base_root = f"https://{base_domain}"
            links = set()
            for a in soup.find_all('a', href=True):
                href = a['href']
                # Only consider internal links
                if href.startswith('/') or base_domain in href:
                    full_url = urljoin(base_url, href)
                    # Remove URL fragments and query params for uniqueness
                    parsed = urlparse(full_url)
                    clean_url = parsed.scheme + '://' + parsed.netloc + parsed.path
                    # Normalize root domain (with/without trailing slash)
                    if clean_url.rstrip('/') == base_root:
                        clean_url = base_root
                    links.add(clean_url)
            # Always include the base_url root domain (no trailing slash)
            links.add(base_root)
            # Remove both root and root/ if both present
            links = {u if u.rstrip('/') != base_root else base_root for u in links}
            # Sort with root domain first
            links = sorted(links, key=lambda u: (u != base_root, u))
            # Limit to max_pages
            links = links[:max_pages]
            results = []
            for url in links:
                try:
                    # Ensure each url has a scheme
                    if not url.lower().startswith(('http://', 'https://')):
                        url = 'https://' + url
                    page_resp = requests.get(url, headers=headers, timeout=8)
                    page_resp.raise_for_status()
                    page_soup = BeautifulSoup(page_resp.content, 'html.parser')
                    title = page_soup.title.string.strip() if page_soup.title and page_soup.title.string else None
                    # Fallback: use first h1 or h2 if no <title>
                    if not title:
                        h1 = page_soup.find('h1')
                        h2 = page_soup.find('h2')
                        if h1 and h1.text.strip():
                            title = h1.text.strip()
                        elif h2 and h2.text.strip():
                            title = h2.text.strip()
                    if not title:
                        title = url  # fallback to URL
                    results.append({"url": url, "title": title, "error": None})
                except Exception as e:
                    results.append({"url": url, "title": None, "error": str(e)})
            logger.info(f"✅ Extracted {len(results)} internal links and titles from {base_url}")
            return results
        except Exception as e:
            logger.error(f"❌ Error extracting internal links from {base_url}: {str(e)}")
            return []
    
    def process_links_group(self, urls: list, item_id: int, description: str = None) -> bool:
        """Scrape all URLs, combine, clean/deduplicate with GPT, and store as one entry."""
        try:
            logger.info(f"🌐 Group scraping {len(urls)} URLs for item {item_id}")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            # Normalize URLs, ensure root domain is first and only once
            norm_urls = []
            seen = set()
            root_url = None
            for u in urls:
                parsed = urlparse(u)
                base_root = f"https://{parsed.netloc}"
                norm = u.rstrip('/')
                if norm == base_root:
                    norm = base_root
                if norm not in seen:
                    seen.add(norm)
                    if norm == base_root:
                        root_url = norm
                        norm_urls.insert(0, norm)
                    else:
                        norm_urls.append(norm)
            if not root_url and norm_urls:
                root_url = norm_urls[0]
            combined_raw = ''
            for url in norm_urls:
                try:
                    resp = requests.get(url, headers=headers, timeout=12)
                    resp.raise_for_status()
                    soup = BeautifulSoup(resp.content, 'html.parser')
                    for script in soup(["script", "style"]):
                        script.decompose()
                    text = soup.get_text()
                    text = self._clean_text_content(text)
                    combined_raw += f"\n\n## Page: {url}\n{text}\n"
                except Exception as e:
                    logger.warning(f"⚠️ Failed to scrape {url}: {str(e)}")
                    continue
            if not combined_raw.strip():
                logger.warning(f"⚠️ No content extracted from any URLs: {urls}")
                return False
            # Clean and structure with GPT
            cleaned_markdown = self.clean_and_structure_content_with_gpt(combined_raw)
            if cleaned_markdown and cleaned_markdown.strip():
                logger.info("✨ Using GPT-cleaned structured markdown for group storage")
                content_to_store = cleaned_markdown
                title = f"Website (Cleaned Group): {root_url or (description or norm_urls[0])}"
            else:
                logger.warning("⚠️ GPT cleaning failed or returned empty. Using fallback combined text.")
                content_to_store = combined_raw
                title = f"Website (Raw Group): {root_url or (description or norm_urls[0])}"
            # Store as one entry
            return self._process_and_store_content(item_id, content_to_store, title)
        except Exception as e:
            logger.error(f"❌ Error in process_links_group: {str(e)}")
            return False
    
    def sync_services_to_knowledge_base(self):
        """Sync all current services into the knowledge base as a markdown table for AI Q&A."""
        if not self.db:
            logger.error("❌ No database connection for syncing services to knowledge base.")
            return False
        try:
            services = self.db.get_services()
            # Remove previous 'Current Services List' entries and their kb_content chunks
            items = self.db.get_all_knowledge_base_items()
            for item in items:
                if item['name'] == 'Current Services List':
                    # Remove related kb_content chunks
                    try:
                        conn = sqlite3.connect(self.db.db_file)
                        cursor = conn.cursor()
                        cursor.execute('DELETE FROM kb_content WHERE source_id = ?', (item['id'],))
                        conn.commit()
                        conn.close()
                        logger.info(f"✅ Removed kb_content chunks for knowledge_base item {item['id']}")
                    except Exception as e:
                        logger.error(f"❌ Error removing kb_content for item {item['id']}: {str(e)}")
                    self.db.remove_knowledge_base_item(item['id'])
            if not services:
                logger.info("✅ No services found; removed Current Services List from knowledge base and kb_content.")
                return True
            # Generate markdown table
            header = "| Service | Price | Duration (min) |\n|---|---|---|"
            rows = [f"| {s['name']} | ${s['price']:.2f} | {s['duration']} |" for s in services]
            markdown = "## Current Services\n\n" + header + "\n" + "\n".join(rows)
            # Add new summary
            success = self.db.add_knowledge_base_item(
                item_type='summary',
                name='Current Services List',
                description='Auto-generated summary of all current services for AI Q&A.',
                content=markdown
            )
            if success:
                # Get the new item's ID
                items = self.db.get_all_knowledge_base_items()
                new_item = next((item for item in items if item['name'] == 'Current Services List'), None)
                if new_item:
                    # Store the whole markdown as a single chunk (special case for services)
                    embedding = self._generate_embedding(markdown)
                    keywords = self._extract_keywords(markdown)
                    conn = sqlite3.connect(self.db.db_file)
                    cursor = conn.cursor()
                    cursor.execute(
                        '''
                        INSERT INTO kb_content 
                        (source_id, content_type, title, content, embedding, keywords, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''',
                        (
                            new_item['id'],
                            'chunk',
                            'Current Services List',
                            markdown,
                            json.dumps(embedding) if embedding else None,
                            json.dumps(keywords),
                            datetime.now().isoformat()
                        )
                    )
                    conn.commit()
                    conn.close()
                    logger.info("✅ Synced and processed current services to knowledge base and kb_content as a single chunk.")
                else:
                    logger.error("❌ Could not find new services summary in knowledge_base after adding.")
            else:
                logger.error("❌ Failed to add services summary to knowledge base.")
            return success
        except Exception as e:
            logger.error(f"❌ Error syncing services to knowledge base: {str(e)}")
            return False