# C:\Users\Dell Lattitude 3450\Desktop\IoT Management - Copy\rule_engine\subscription_service.py

import requests
import json
from datetime import datetime
from sqlalchemy import text


class SMSService:
    def __init__(self, db, app):
        self.db = db
        self.app = app

        # 🔥 Replace with your real SMS API
        self.sms_api_url = "https://api.yoursmsgateway.com/send"
        self.api_key = "YOUR_API_KEY"

    # -------------------------------------------------
    # Check subscription quota
    # -------------------------------------------------
    def check_sms_quota(self, company_id):
        query = """
        SELECT sms_limit, sms_used 
        FROM company_subscriptions
        WHERE company_id = :company_id 
        AND is_active = 1
        """

        result = self.db.session.execute(
            text(query),
            {"company_id": company_id}
        ).fetchone()

        if not result:
            return False

        sms_limit, sms_used = result

        return sms_used < sms_limit

    # -------------------------------------------------
    # Deduct SMS usage
    # -------------------------------------------------
    def increment_sms_usage(self, company_id):
        query = """
        UPDATE company_subscriptions
        SET sms_used = sms_used + 1
        WHERE company_id = :company_id
        """

        self.db.session.execute(text(query), {"company_id": company_id})
        self.db.session.commit()

    # -------------------------------------------------
    # Send SMS
    # -------------------------------------------------
    def send_sms(self, company_id, phone_number, message):

        if not self.check_sms_quota(company_id):
            print("❌ SMS quota exceeded")
            return False

        try:
            payload = {
                "api_key": self.api_key,
                "to": phone_number,
                "message": message
            }

            response = requests.post(self.sms_api_url, json=payload)

            if response.status_code == 200:
                self.increment_sms_usage(company_id)
                return True

            return False

        except Exception as e:
            print("❌ SMS error:", e)
            return False