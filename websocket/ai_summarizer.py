import openai
import os
import logging
import json
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class AISummarizer:
    """Dedicated AI service for generating summaries of calls and messages"""
    
    def __init__(self, database_service=None):
        self.client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.db = database_service
        
        # Summary generation settings
        self.summary_settings = {
            'model': 'gpt-4.1-nano',
            'temperature': 0.3,
            'max_tokens': 150
        }
    
    def summarize_call_transcript(self, transcript: List[Dict], customer_name: str = None, phone: str = None) -> Dict:
        """
        Generate a summary for a voice call transcript AND extract customer name
        
        Args:
            transcript: List of conversation messages with speaker, text, and time
            customer_name: Customer name if available
            phone: Customer phone number
            
        Returns:
            Dict with 'summary' and 'customer_name' (or None if no name found)
        """
        try:
            if not transcript or len(transcript) == 0:
                return {"summary": "No conversation content to summarize", "customer_name": None}
            
            # Format transcript for AI analysis
            conversation_text = self._format_transcript_for_analysis(transcript)
            
            # Create summary and name extraction prompt
            prompt = f"""Analyze this voice call transcript from Radiance MD Med Spa and provide:
1. A concise summary
2. The customer's first name (if mentioned)

TRANSCRIPT:
{conversation_text}

INSTRUCTIONS:
- Summarize the main purpose of the call in 1-2 sentences
- Mention any appointments booked, services discussed, or issues raised
- Extract ONLY the customer's first name (ignore last names)
- If no name found, return "None" for customer_name
- Keep summary under 60 words
- Focus on actionable information and outcomes

Respond with JSON format:
{{
  "summary": "summary text here",
  "customer_name": "first_name_only" or null
}}"""

            response = self.client.chat.completions.create(
                model=self.summary_settings['model'],
                messages=[
                    {"role": "system", "content": "You are an AI assistant that creates concise, professional summaries of customer service calls for a medical spa and extracts customer names. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.summary_settings['temperature'],
                max_tokens=self.summary_settings['max_tokens']
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Parse JSON response
            try:
                result = json.loads(result_text)
                summary = result.get("summary", "Unable to generate summary")
                extracted_name = result.get("customer_name")
                
                # Log the AI's name extraction
                if extracted_name and extracted_name.lower() != "none":
                    logger.info(f"👤 AI extracted customer name from voice call: '{extracted_name}' for {phone}")
                else:
                    logger.info(f"👤 AI found no customer name in voice call for {phone}")
                
                # NEW: Check database for customer name override
                database_name = self._get_database_customer_name(phone)
                final_name = database_name if database_name else extracted_name
                
                if database_name and database_name != extracted_name:
                    logger.info(f"👤 Using database name override: '{database_name}' (AI extracted: '{extracted_name}') for {phone}")
                elif database_name:
                    logger.info(f"👤 Database name matches AI extraction: '{database_name}' for {phone}")
                
                logger.info(f"✅ Generated call summary: {summary[:50]}...")
                return {"summary": summary, "customer_name": final_name}
                
            except json.JSONDecodeError as e:
                logger.error(f"❌ Failed to parse AI response JSON: {e}")
                logger.error(f"❌ Raw response: {result_text}")
                
                # Try to fix common JSON formatting issues
                try:
                    # Fix missing comma between summary and customer_name
                    if '"summary":' in result_text and '"customer_name":' in result_text:
                        # Look for the pattern: "summary": "..." "customer_name":
                        import re
                        fixed_text = re.sub(r'("summary":\s*"[^"]*")\s*("customer_name":)', r'\1,\2', result_text)
                        result = json.loads(fixed_text)
                        summary = result.get("summary", "Unable to generate summary")
                        extracted_name = result.get("customer_name")
                        
                        logger.info(f"🔧 Fixed JSON formatting issue for {phone}")
                        
                        # NEW: Check database for customer name override
                        database_name = self._get_database_customer_name(phone)
                        final_name = database_name if database_name else extracted_name
                        
                        logger.info(f"✅ Generated call summary (after JSON fix): {summary[:50]}...")
                        return {"summary": summary, "customer_name": final_name}
                except:
                    pass
                
                # Fallback to just summary
                return {"summary": result_text, "customer_name": None}
            
        except Exception as e:
            logger.error(f"❌ Error generating call summary: {str(e)}")
            return {"summary": "Unable to generate summary at this time", "customer_name": None}
    
    def summarize_sms_conversation(self, messages: List[Dict], customer_name: str = None, phone: str = None) -> Dict:
        """
        Generate a summary for an SMS conversation AND extract customer name
        
        Args:
            messages: List of SMS messages with sender, message, and timestamp
            customer_name: Customer name if available
            phone: Customer phone number
            
        Returns:
            Dict with 'summary' and 'customer_name' (or None if no name found)
        """
        try:
            if not messages or len(messages) == 0:
                return {"summary": "No conversation content to summarize", "customer_name": None}
            
            # Format messages for AI analysis
            conversation_text = self._format_messages_for_analysis(messages)
            
            # Create summary and name extraction prompt
            prompt = f"""Analyze this SMS conversation between a customer and Radiance MD Med Spa's AI assistant and provide:
1. A concise summary
2. The customer's first name (if mentioned)

CONVERSATION:
{conversation_text}

INSTRUCTIONS:
- Summarize the main purpose of the conversation in 1-2 sentences
- Mention any appointments booked, services discussed, or issues raised
- Extract ONLY the customer's first name (ignore last names)
- If no name found, return "None" for customer_name
- Keep summary under 60 words
- Focus on actionable information and outcomes

Respond with JSON format:
{{
  "summary": "summary text here",
  "customer_name": "first_name_only" or null
}}"""

            response = self.client.chat.completions.create(
                model=self.summary_settings['model'],
                messages=[
                    {"role": "system", "content": "You are an AI assistant that creates concise, professional summaries of customer service SMS conversations for a medical spa and extracts customer names. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.summary_settings['temperature'],
                max_tokens=self.summary_settings['max_tokens']
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Parse JSON response
            try:
                result = json.loads(result_text)
                summary = result.get("summary", "Unable to generate summary")
                extracted_name = result.get("customer_name")
                
                # Log the AI's name extraction
                if extracted_name and extracted_name.lower() != "none":
                    logger.info(f"👤 AI extracted customer name from SMS: '{extracted_name}' for {phone}")
                else:
                    logger.info(f"👤 AI found no customer name in SMS for {phone}")
                
                # NEW: Check database for customer name override
                database_name = self._get_database_customer_name(phone)
                final_name = database_name if database_name else extracted_name
                
                if database_name and database_name != extracted_name:
                    logger.info(f"👤 Using database name override: '{database_name}' (AI extracted: '{extracted_name}') for {phone}")
                elif database_name:
                    logger.info(f"👤 Database name matches AI extraction: '{database_name}' for {phone}")
                
                logger.info(f"✅ Generated SMS summary: {summary[:50]}...")
                return {"summary": summary, "customer_name": final_name}
                
            except json.JSONDecodeError as e:
                logger.error(f"❌ Failed to parse AI response JSON: {e}")
                logger.error(f"❌ Raw response: {result_text}")
                
                # Try to fix common JSON formatting issues
                try:
                    # Fix missing comma between summary and customer_name
                    if '"summary":' in result_text and '"customer_name":' in result_text:
                        # Look for the pattern: "summary": "..." "customer_name":
                        import re
                        fixed_text = re.sub(r'("summary":\s*"[^"]*")\s*("customer_name":)', r'\1,\2', result_text)
                        result = json.loads(fixed_text)
                        summary = result.get("summary", "Unable to generate summary")
                        extracted_name = result.get("customer_name")
                        
                        logger.info(f"🔧 Fixed JSON formatting issue for {phone}")
                        
                        # NEW: Check database for customer name override
                        database_name = self._get_database_customer_name(phone)
                        final_name = database_name if database_name else extracted_name
                        
                        logger.info(f"✅ Generated SMS summary (after JSON fix): {summary[:50]}...")
                        return {"summary": summary, "customer_name": final_name}
                except:
                    pass
                
                # Fallback to just summary
                return {"summary": result_text, "customer_name": None}
            
        except Exception as e:
            logger.error(f"❌ Error generating SMS summary: {str(e)}")
            return {"summary": "Unable to generate summary at this time", "customer_name": None}
    
    def _format_transcript_for_analysis(self, transcript: List[Dict]) -> str:
        """Format voice call transcript for AI analysis"""
        formatted_lines = []
        
        for message in transcript:
            speaker = "Customer" if message.get('speaker') == 'customer' else "AI Assistant"
            text = message.get('text', '')
            time = message.get('time', '')
            
            formatted_lines.append(f"[{time}] {speaker}: {text}")
        
        return "\n".join(formatted_lines)
    
    def _format_messages_for_analysis(self, messages: List[Dict]) -> str:
        """Format SMS messages for AI analysis"""
        formatted_lines = []
        
        for message in messages:
            sender = "Customer" if message.get('sender') == 'customer' else "AI Assistant"
            text = message.get('message', '')
            timestamp = message.get('timestamp', '')
            
            formatted_lines.append(f"[{timestamp}] {sender}: {text}")
        
        return "\n".join(formatted_lines)
    
    def _get_database_customer_name(self, phone: str) -> Optional[str]:
        """
        Get customer name from database if available
        
        Args:
            phone: Customer phone number
            
        Returns:
            Customer name from database or None if not found
        """
        if not self.db or not phone:
            return None
            
        try:
            customer = self.db.get_customer(phone)
            if customer and customer.get('name'):
                logger.info(f"👤 Found customer name in database: '{customer['name']}' for {phone}")
                return customer['name']
            else:
                logger.info(f"👤 No customer found in database for {phone}")
                return None
        except Exception as e:
            logger.error(f"❌ Error getting customer name from database: {str(e)}")
            return None
    
    def analyze_for_notifications(self, summary: str, transcript_or_messages: List[Dict], 
                                conversation_type: str, phone: str, customer_name: str = None) -> Optional[Dict]:
        """
        Analyze conversation for notification-worthy issues
        
        Args:
            summary: Generated summary of the conversation
            transcript_or_messages: Raw conversation data
            conversation_type: 'voice' or 'sms'
            phone: Customer phone number
            customer_name: Customer name if available
            
        Returns:
            Dict with notification details if issue found, None otherwise
        """
        try:
            # Log the summary being used for notification detection
            logger.info(f"👽 Notification detection using summary: {summary}")
            # Format conversation for analysis
            if conversation_type == 'voice':
                conversation_text = self._format_transcript_for_analysis(transcript_or_messages)
            else:
                conversation_text = self._format_messages_for_analysis(transcript_or_messages)
            
            # Create notification analysis prompt - FIXED: Removed problematic f-string
            prompt = f"""Analyze this customer service conversation for issues that require human attention.

CONVERSATION SUMMARY: {summary}

FULL CONVERSATION:
{conversation_text}

ANALYSIS INSTRUCTIONS:
Look for these types of issues:

CRITICAL (immediate attention needed):
- Customer explicitly asks to speak to a human/real person
- Customer expresses anger, frustration, or dissatisfaction
- AI unable to resolve customer's query after multiple attempts
- Payment or billing issues
- Medical concerns or complications
- Complaints about service quality

URGENT (action needed soon):
- Appointment reschedule/cancellation requests
- Payment failures during booking
- Customer has specific requirements AI couldn't handle
- Follow-up needed for incomplete bookings

INTEREST (potential business opportunity):
If the CONVERSATION SUMMARY mentions that customer shows interest but no appointments were booked, trigger an INTEREST notification
ALWAYS TRIGGER WHEN the customer's behavior or conversation matches any of the following:
- The customer is a warm lead who could convert with follow-up
- The customer asks about multiple services but does not book
- The customer asks about pricing but does not commit
- The customer asks general questions about services, staff, or spa operations
- The customer expresses curiosity about treatments or procedures


Respond with JSON format only. If no significant issues found, respond with: {{"has_issue": false}}

If an issue is found, respond with:
{{
  "has_issue": true,
  "type": "critical" or "urgent" or "interest",
  "title": "Brief title describing the issue",
  "summary": "1-2 sentence explanation of what needs attention"
}}

RESPONSE:"""

            response = self.client.chat.completions.create(
                model=self.summary_settings['model'],
                messages=[
                    {"role": "system", "content": "You are an AI assistant that analyzes customer service conversations to identify issues requiring human attention. Always respond with valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4,  # Lower temperature for more consistent JSON
                max_tokens=200
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Parse JSON response
            try:
                result = json.loads(result_text)
                
                if result.get('has_issue', False):
                    notification = {
                        'type': result.get('type', 'interest'),
                        'title': result.get('title', 'Customer Issue Detected'),
                        'summary': result.get('summary', 'Issue requires attention'),
                        'phone': phone,
                        'customer_name': customer_name,
                        'conversation_type': conversation_type
                    }
                    
                    logger.info(f"🚨 Notification detected: {notification['type']} - {notification['title']}")
                    return notification
                else:
                    logger.info("✅ No notification-worthy issues detected")
                    return None
                    
            except json.JSONDecodeError as e:
                logger.error(f"❌ Failed to parse notification analysis JSON: {e}")
                logger.error(f"❌ Raw response: {result_text}")
                return None
            
        except Exception as e:
            logger.error(f"❌ Error analyzing for notifications: {str(e)}")
            return None