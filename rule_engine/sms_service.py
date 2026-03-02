#C:\Users\Dell Lattitude 3450\Desktop\IoT Management - Copy\rule_engine\sms_service.py
import requests
from sqlalchemy import text
from datetime import datetime

AUTH_KEY = "Y8u0ioDk1V2QK5wBNBJP"
AUTH_TOKEN = "S0ESOZ7yvpLZpXnojPibrySynHQTlqq331yyzI3q"
BASE_URL = f"https://restapi.smscountry.com/v0.1/Accounts/{AUTH_KEY}/SMSes"
SENDER_ID = "KLEIOT"


class SMSService:

    def __init__(self, db, app):
        self.db = db
        self.app = app

    def check_sms_quota(self, company_id):
        try:
            result = self.db.session.execute(text("""
                SELECT sms_limit, sms_used
                FROM company_subscriptions
                WHERE company_id = :company_id
                AND is_active = 1
            """), {"company_id": company_id}).fetchone()

            if not result:
                print("⚠️ No subscription found")
                return False

            sms_limit, sms_used = result
            return sms_used < sms_limit

        except Exception as e:
            print("❌ Error checking SMS quota:", e)
            return False

    def send_sms(self, company_id, phone, message):
        try:
            payload = {
                "Text": message,
                "Number": phone,
                "SenderId": SENDER_ID,
                "DRNotifyUrl": "",
                "DRNotifyHttpMethod": "POST",
                "Tool": "API"
            }

            response = requests.post(
                BASE_URL,
                auth=(AUTH_KEY, AUTH_TOKEN),
                json=payload,
                timeout=10
            )

            if response.status_code in [200, 202]:
                # Deduct SMS usage
                self.db.session.execute(text("""
                    UPDATE company_subscriptions
                    SET sms_used = sms_used + 1
                    WHERE company_id = :company_id
                    AND is_active = 1
                """), {"company_id": company_id})

                self.db.session.commit()
                print(f"✅ SMS sent to {phone}")
                return True
            else:
                print("❌ SMS API error:", response.text)
                return False

        except Exception as e:
            print("❌ SMS send error:", e)
            self.db.session.rollback()
            return False