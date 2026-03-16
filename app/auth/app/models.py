from database import db


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    username = db.Column(db.String(100), nullable=False)


class CustomCategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(40), nullable=False)
    prompt_instruction = db.Column(db.Text, nullable=False)
    examples = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.now())

    user = db.relationship('User', backref=db.backref('custom_categories', lazy=True))

    __table_args__ = (
        db.UniqueConstraint('user_id', 'name', name='uq_user_category_name'),
    )
