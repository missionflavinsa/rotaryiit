from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class ClassRoom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    section = db.Column(db.String(10), nullable=False)
    rows = db.Column(db.Integer, default=5)
    columns = db.Column(db.Integer, default=4) # This will be the max columns in any row
    bench_type = db.Column(db.String(20), default='double') # 'single' or 'double'
    row_layout = db.Column(db.String(500)) # comma-separated list of benches per row, e.g., "5,6,5"
    capacity = db.Column(db.Integer, nullable=False)
    students = db.relationship('Student', backref='classroom', lazy=True)

    def get_row_layout(self):
        if not self.row_layout:
            return [self.columns] * self.rows
        try:
            return [int(x.strip()) for x in self.row_layout.split(',')]
        except:
            return [self.columns] * self.rows

    def update_capacity(self):
        layout = self.get_row_layout()
        multiplier = 1 if self.bench_type == 'single' else 2
        self.capacity = sum(layout) * multiplier
        self.rows = len(layout)
        self.columns = max(layout) if layout else 0

    def __repr__(self):
        return f'<ClassRoom {self.name} {self.section}>'

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    roll_number = db.Column(db.String(20), unique=True, nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class_room.id'), nullable=False)

    def __repr__(self):
        return f'<Student {self.name} {self.roll_number}>'

class Supervisor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))

    def __repr__(self):
        return f'<Supervisor {self.name}>'

class Test(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    duration = db.Column(db.Integer, default=180) # in minutes
    paper_sets = db.Column(db.String(50), default='A,B,C,D')
    target_classes_json = db.Column(db.Text) # JSON list of class IDs taking the exam
    exam_blocks_json = db.Column(db.Text) # JSON list of {room_id, supervisor_id}
    classes_json = db.Column(db.Text) # Legacy field, keeping for compatibility but will migrate logic

    def __repr__(self):
        return f'<Test {self.title}>'

class SeatingArrangement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('test.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('class_room.id'), nullable=False)
    supervisor_id = db.Column(db.Integer, db.ForeignKey('supervisor.id'))
    seat_number = db.Column(db.Integer, nullable=False)
    paper_set = db.Column(db.String(5))

    student = db.relationship('Student', backref='seating')
    room = db.relationship('ClassRoom', backref='seating')
    test = db.relationship('Test', backref='arrangements')
    supervisor = db.relationship('Supervisor', backref='arrangements')
