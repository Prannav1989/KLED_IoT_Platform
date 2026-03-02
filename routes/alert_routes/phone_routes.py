# routes/alert_routes/phone_routes.py

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import text
from extensions import db

phone_bp = Blueprint(
    "phone",
    __name__,
    url_prefix="/phones"
)

# -----------------------------------------------------
# LIST PHONE NUMBERS
# -----------------------------------------------------
@phone_bp.route("/")
@login_required
def list_phones():

    # If super admin → show all phones
    if current_user.role == "super_admin":
        phones = db.session.execute(text("""
            SELECT p.id, p.phone_number, p.recipient_name,
                   p.is_active, p.created_at,
                   c.name as company_name
            FROM phone_numbers p
            JOIN companies c ON p.company_id = c.id
            ORDER BY p.created_at DESC
        """)).fetchall()

        companies = db.session.execute(text("""
            SELECT id, name FROM companies ORDER BY name
        """)).fetchall()

    else:
        phones = db.session.execute(text("""
            SELECT p.id, p.phone_number, p.recipient_name,
                   p.is_active, p.created_at,
                   c.name as company_name
            FROM phone_numbers p
            JOIN companies c ON p.company_id = c.id
            WHERE p.company_id = :company_id
            ORDER BY p.created_at DESC
        """), {
            "company_id": current_user.company_id
        }).fetchall()

        companies = None

    return render_template(
        "alerts/phone_list.html",
        phones=phones,
        companies=companies
    )

# -----------------------------------------------------
# ADD PHONE NUMBER
# -----------------------------------------------------
@phone_bp.route("/add", methods=["POST"])
@login_required
def add_phone():

    phone = request.form["phone_number"]
    name = request.form.get("recipient_name", "")

    # If super admin → selected company
    if current_user.role == "super_admin":
        company_id = request.form.get("company_id")
    else:
        company_id = current_user.company_id

    db.session.execute(text("""
        INSERT INTO phone_numbers
        (company_id, phone_number, recipient_name, created_by)
        VALUES (:company_id, :phone, :name, :user_id)
    """), {
        "company_id": company_id,
        "phone": phone,
        "name": name,
        "user_id": current_user.id
    })

    db.session.commit()

    flash("Phone number added successfully", "success")
    return redirect(url_for("phone.list_phones"))

# -----------------------------------------------------
# ACTIVATE / DEACTIVATE
# -----------------------------------------------------
@phone_bp.route("/toggle/<int:phone_id>")
@login_required
def toggle_phone(phone_id):

    db.session.execute(text("""
        UPDATE phone_numbers
        SET is_active = NOT is_active
        WHERE id = :phone_id
        AND company_id = :company_id
    """), {
        "phone_id": phone_id,
        "company_id": current_user.company_id
    })

    db.session.commit()

    flash("Phone status updated", "info")
    return redirect(url_for("phone.list_phones"))