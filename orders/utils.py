from twilio.rest import Client
from django.conf import settings


# =====================================
# SEND WHATSAPP INVOICE
# =====================================

def send_whatsapp_invoice(order, invoice_data):

    try:
        # Twilio Credentials (Put in settings.py)
        account_sid = settings.TWILIO_ACCOUNT_SID
        auth_token = settings.TWILIO_AUTH_TOKEN
        from_number = settings.TWILIO_WHATSAPP_FROM

        client = Client(account_sid, auth_token)

        # Customer phone (with country code)
        to_number = f"whatsapp:+91{order.customer_phone}"

        # Message Format
        message_body = f"""
🧾 *CAFEFLOW INVOICE*

Bill No: {invoice_data['bill']}
Customer: {invoice_data['customer']}

Total Amount: ₹{invoice_data['total']}

Thank you for visiting 🙏
Visit Again 😊
"""

        # Send message
        message = client.messages.create(
            body=message_body,
            from_=from_number,
            to=to_number
        )

        return True

    except Exception as e:
        print("WhatsApp Error:", e)
        return False