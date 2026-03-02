# rule_engine/email_service.py

import smtplib
from email.mime.text import MIMEText
from sqlalchemy import text


class EmailService:
    def __init__(self, db, app):
        self.db = db
        self.app = app

        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        self.sender_email = "your@email.com"
        self.sender_password = "APP_PASSWORD"

    # -------------------------------------------------
    def check_email_quota(self, company_id):

        query = """
        SELECT email_limit, email_used 
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

        email_limit, email_used = result
        return email_used < email_limit

    # -------------------------------------------------
    def increment_email_usage(self, company_id):
        query = """
        UPDATE company_subscriptions
        SET email_used = email_used + 1
        WHERE company_id = :company_id
        """

        self.db.session.execute(text(query), {"company_id": company_id})
        self.db.session.commit()

    # -------------------------------------------------
    def send_email(self, company_id, recipient, subject, body):

        if not self.check_email_quota(company_id):
            print("❌ Email quota exceeded")
            return False

        try:
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = self.sender_email
            msg["To"] = recipient

            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.sender_email, self.sender_password)
            server.sendmail(self.sender_email, recipient, msg.as_string())
            server.quit()

            self.increment_email_usage(company_id)
            return True

        except Exception as e:
            print("❌ Email error:", e)
            return False