from app import app, db

with app.app_context():
    db.create_all()
    print("NoticeForm table created (if it did not exist).")