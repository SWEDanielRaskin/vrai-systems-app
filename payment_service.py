# payment_service.py
import os
import requests
import logging
import json
from datetime import datetime, timedelta
import uuid

logger = logging.getLogger(__name__)

class PaymentService:
    """Service for handling show-up deposits via Square API"""
    
    def __init__(self):
        self.access_token = os.getenv('SQUARE_ACCESS_TOKEN')
        self.application_id = os.getenv('SQUARE_APPLICATION_ID')
        self.environment = os.getenv('SQUARE_ENVIRONMENT', 'sandbox')  # 'sandbox' or 'production'
        
        # Set base URL based on environment
        if self.environment == 'production':
            self.base_url = 'https://connect.squareup.com'
        else:
            self.base_url = 'https://connect.squareupsandbox.com'
        
        # Default deposit amount (in cents)
        self.default_deposit_amount = 5000  # $50.00
        
        # Store payment records locally for tracking
        self.payments_file = 'payments.json'
    
    def create_deposit_payment_link(self, appointment_data):
        """
        Create a Square payment link for show-up deposit
        
        Args:
            appointment_data: Dict with appointment details
            
        Returns:
            Dict with payment link and tracking info
        """
        try:
            # Generate unique idempotency key
            idempotency_key = str(uuid.uuid4())
            
            # Calculate deposit amount (could vary by service in future)
            deposit_amount = self.get_deposit_amount(appointment_data.get('service'))
            
            # Format phone number for Square (they're very strict about format)
            phone_number = appointment_data.get('phone', '')
            formatted_phone = self.format_phone_for_square(phone_number)
            
            # Create payment request (removing problematic pre_populated_data for now)
            payment_request = {
                "idempotency_key": idempotency_key,
                "ask_for_shipping_address": False,
                "merchant_support_email": "info@omorfiamedspa.com",
                "redirect_url": "https://omorfiamedspa.com/deposit-confirmation",  # Your success page
                "order": {
                    "location_id": os.getenv('SQUARE_LOCATION_ID'),
                    "line_items": [
                        {
                            "name": f"Show-up Deposit - {appointment_data.get('service_name', 'Appointment')}",
                            "quantity": "1",
                            "base_price_money": {
                                "amount": deposit_amount,
                                "currency": "USD"
                            },
                            "note": f"Deposit for {appointment_data.get('name')} - {appointment_data.get('date')} {appointment_data.get('time')}"
                        }
                    ]
                }
            }
            
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json',
                'Square-Version': '2023-10-18'
            }
            
            logger.info(f"💳 Creating payment link for {appointment_data.get('name')} - ${deposit_amount/100}")
            
            response = requests.post(
                f"{self.base_url}/v2/online-checkout/payment-links",
                headers=headers,
                json=payment_request
            )
            
            if response.status_code == 200:
                result = response.json()
                payment_link = result.get('payment_link', {})
                
                # Store payment record for tracking
                payment_record = {
                    'payment_link_id': payment_link.get('id'),
                    'order_id': payment_link.get('order_id'),
                    'appointment_id': appointment_data.get('id'),
                    'customer_name': appointment_data.get('name'),
                    'customer_phone': appointment_data.get('phone'),
                    'amount': deposit_amount,
                    'status': 'pending',
                    'created_at': datetime.now().isoformat(),
                    'appointment_date': appointment_data.get('date'),
                    'appointment_time': appointment_data.get('time'),
                    'service': appointment_data.get('service')
                }
                
                self.save_payment_record(payment_record)
                
                logger.info(f"✅ Payment link created: {payment_link.get('url')}")
                
                return {
                    'success': True,
                    'payment_url': payment_link.get('url'),
                    'payment_link_id': payment_link.get('id'),
                    'order_id': payment_link.get('order_id'),
                    'amount': deposit_amount / 100,  # Convert to dollars for display
                    'record': payment_record
                }
            else:
                logger.error(f"❌ Square API error: {response.status_code} - {response.text}")
                return {
                    'success': False,
                    'error': f"Payment link creation failed: {response.status_code}"
                }
                
        except Exception as e:
            logger.error(f"❌ Error creating payment link: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def format_phone_for_square(self, phone):
        """
        Format phone number specifically for Square API requirements
        Square expects E.164 format: +1XXXXXXXXXX
        """
        if not phone:
            return None
            
        # Remove all non-digit characters
        digits_only = ''.join(filter(str.isdigit, phone))
        
        # Handle different input formats
        if len(digits_only) == 10:
            # US number without country code: 3132044895 -> +13132044895
            return f"+1{digits_only}"
        elif len(digits_only) == 11 and digits_only.startswith('1'):
            # US number with country code: 13132044895 -> +13132044895
            return f"+{digits_only}"
        elif phone.startswith('+1') and len(digits_only) == 11:
            # Already in correct format
            return phone
        else:
            # Default: assume US number and add +1
            return f"+1{digits_only[-10:]}" if len(digits_only) >= 10 else None
    
    def get_deposit_amount(self, service):
        """
        Get deposit amount based on service type
        Future: Could vary by service
        """
        # Service-specific deposits (in cents)
        service_deposits = {
            'botox': 5000,           # $50
            'hydrafacial': 5000,     # $50
            'laser_hair_removal': 5000,  # $50
            'microneedling': 5000,   # $50
        }
        
        return service_deposits.get(service, self.default_deposit_amount)
    
    def check_payment_status(self, payment_link_id):
        """Check if payment has been completed"""
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Square-Version': '2023-10-18'
            }
            
            response = requests.get(
                f"{self.base_url}/v2/online-checkout/payment-links/{payment_link_id}",
                headers=headers
            )
            
            if response.status_code == 200:
                result = response.json()
                payment_link = result.get('payment_link', {})
                order_id = payment_link.get('order_id')
                
                # Check order status
                order_response = requests.get(
                    f"{self.base_url}/v2/orders/{order_id}",
                    headers=headers
                )
                
                if order_response.status_code == 200:
                    order_data = order_response.json()
                    order = order_data.get('order', {})
                    state = order.get('state')  # 'OPEN', 'COMPLETED', 'CANCELED'
                    
                    return {
                        'success': True,
                        'status': state.lower() if state else 'unknown',
                        'order': order
                    }
            
            return {'success': False, 'error': 'Could not check payment status'}
            
        except Exception as e:
            logger.error(f"❌ Error checking payment status: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def process_refund(self, payment_record, reason="Customer showed up"):
        """
        Process refund for show-up deposit
        
        Args:
            payment_record: Payment record from local storage
            reason: Reason for refund
            
        Returns:
            Dict with refund result
        """
        try:
            # First, check if payment was actually completed
            status_check = self.check_payment_status(payment_record['payment_link_id'])
            
            if not status_check['success'] or status_check['status'] != 'completed':
                return {
                    'success': False,
                    'error': 'Payment not completed, cannot refund'
                }
            
            # Get the payment ID from the order
            order = status_check['order']
            tenders = order.get('tenders', [])
            
            if not tenders:
                return {
                    'success': False,
                    'error': 'No payment found for this order'
                }
            
            payment_id = tenders[0].get('id')
            amount_to_refund = payment_record['amount']
            
            # Create refund request
            refund_request = {
                "idempotency_key": str(uuid.uuid4()),
                "amount_money": {
                    "amount": amount_to_refund,
                    "currency": "USD"
                },
                "payment_id": payment_id,
                "reason": reason
            }
            
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json',
                'Square-Version': '2023-10-18'
            }
            
            logger.info(f"💰 Processing refund for {payment_record['customer_name']} - ${amount_to_refund/100}")
            
            response = requests.post(
                f"{self.base_url}/v2/refunds",
                headers=headers,
                json=refund_request
            )
            
            if response.status_code == 200:
                result = response.json()
                refund = result.get('refund', {})
                
                # Update payment record
                payment_record['status'] = 'refunded'
                payment_record['refund_id'] = refund.get('id')
                payment_record['refunded_at'] = datetime.now().isoformat()
                payment_record['refund_reason'] = reason
                
                self.update_payment_record(payment_record)
                
                logger.info(f"✅ Refund processed: {refund.get('id')}")
                
                return {
                    'success': True,
                    'refund_id': refund.get('id'),
                    'amount_refunded': amount_to_refund / 100,
                    'status': refund.get('status')
                }
            else:
                logger.error(f"❌ Refund failed: {response.status_code} - {response.text}")
                return {
                    'success': False,
                    'error': f"Refund failed: {response.status_code}"
                }
                
        except Exception as e:
            logger.error(f"❌ Error processing refund: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def save_payment_record(self, payment_record):
        """Save payment record to local file"""
        try:
            # Load existing records
            records = []
            if os.path.exists(self.payments_file):
                with open(self.payments_file, 'r') as f:
                    records = json.load(f)
            
            # Add new record
            records.append(payment_record)
            
            # Save back to file
            with open(self.payments_file, 'w') as f:
                json.dump(records, f, indent=2)
            
            logger.info(f"💾 Payment record saved for {payment_record['customer_name']}")
            
        except Exception as e:
            logger.error(f"❌ Error saving payment record: {str(e)}")
    
    def update_payment_record(self, updated_record):
        """Update existing payment record"""
        try:
            records = []
            if os.path.exists(self.payments_file):
                with open(self.payments_file, 'r') as f:
                    records = json.load(f)
            
            # Find and update the record
            for i, record in enumerate(records):
                if record['payment_link_id'] == updated_record['payment_link_id']:
                    records[i] = updated_record
                    break
            
            # Save back to file
            with open(self.payments_file, 'w') as f:
                json.dump(records, f, indent=2)
            
            logger.info(f"💾 Payment record updated for {updated_record['customer_name']}")
            
        except Exception as e:
            logger.error(f"❌ Error updating payment record: {str(e)}")
    
    def get_payment_by_appointment(self, appointment_id):
        """Get payment record by appointment ID"""
        try:
            if not os.path.exists(self.payments_file):
                return None
            
            with open(self.payments_file, 'r') as f:
                records = json.load(f)
            
            for record in records:
                if record['appointment_id'] == appointment_id:
                    return record
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting payment record: {str(e)}")
            return None