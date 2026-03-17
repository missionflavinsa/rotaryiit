from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_migrate import Migrate
from models import db, ClassRoom, Student, Supervisor, Test, SeatingArrangement
import json
import os
import pandas as pd
from io import BytesIO
from datetime import datetime

app = Flask(__name__)

# Heroku Postgres URI fix (it uses 'postgres://' which SQLAlchemy requires 'postgresql://')
uri = os.environ.get('DATABASE_URL', 'sqlite:///rotary_iit.db')
if uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_secret_key')
app.config['UPLOAD_FOLDER'] = 'uploads'

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db.init_app(app)
migrate = Migrate(app, db)

# --- Template Filters ---
@app.template_filter('from_json')
def from_json_filter(s):
    return json.loads(s) if s else []

@app.template_filter('room_name')
def room_name_filter(room_id):
    room = db.session.get(ClassRoom, room_id)
    return f"{room.name} - {room.section}" if room else "Unknown"

@app.template_filter('supervisor_name')
def supervisor_name_filter(supervisor_id):
    if not supervisor_id: return "None"
    supervisor = Supervisor.query.get(supervisor_id)
    return supervisor.name if supervisor else "Unknown"

@app.route('/')
def index():
    stats = {
        'classes': ClassRoom.query.count(),
        'students': Student.query.count(),
        'tests': Test.query.count(),
        'supervisors': Supervisor.query.count()
    }
    return render_template('index.html', stats=stats)

# --- Bulk Import ---
@app.route('/import', methods=['GET', 'POST'])
def bulk_import():
    if request.method == 'POST':
        file = request.files.get('file')
        import_type = request.form.get('type')
        if file and file.filename.endswith(('.xlsx', '.csv')):
            try:
                if file.filename.endswith('.csv'):
                    df = pd.read_csv(file)
                else:
                    df = pd.read_excel(file)
                
                if import_type == 'classes':
                    for _, row in df.iterrows():
                        new_class = ClassRoom(name=row['Name'], section=row['Section'], capacity=row['Capacity'])
                        db.session.add(new_class)
                elif import_type == 'students':
                    for _, row in df.iterrows():
                        # Find class by name and section
                        cls_name, cls_sec = str(row['Class']).split('-')
                        cls = ClassRoom.query.filter_by(name=cls_name, section=cls_sec).first()
                        if cls:
                            new_student = Student(name=row['Name'], roll_number=row['Roll Number'], class_id=cls.id)
                            db.session.add(new_student)
                
                db.session.commit()
                flash(f'Imported {len(df)} {import_type} successfully!')
            except Exception as e:
                db.session.rollback()
                flash(f'Error importing: {str(e)}', 'error')
            return redirect(url_for('index'))
    return render_template('import.html')

@app.route('/import/template/<type>')
def download_template(type):
    output = BytesIO()
    if type == 'classes':
        df = pd.DataFrame(columns=['Name', 'Section', 'Capacity'])
    else:
        df = pd.DataFrame(columns=['Name', 'Roll Number', 'Class']) # Class as Grade 10-A
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name=f'{type}_template.xlsx')

# --- Class CRUD ---
@app.route('/classes')
def list_classes():
    classes = ClassRoom.query.all()
    return render_template('classes.html', classes=classes)

@app.route('/classes/add', methods=['GET', 'POST'])
def add_class():
    if request.method == 'POST':
        name = request.form['name']
        section = request.form['section']
        rows = int(request.form.get('rows', 5))
        columns = int(request.form.get('columns', 4))
        bench_type = request.form.get('bench_type', 'double')
        row_layout = request.form.get('row_layout')
        
        new_class = ClassRoom(
            name=name, 
            section=section, 
            bench_type=bench_type, 
            row_layout=row_layout
        )
        new_class.update_capacity()
        
        db.session.add(new_class)
        db.session.commit()
        flash('Class added successfully!')
        return redirect(url_for('list_classes'))
    return render_template('class_form.html', action='Add')

@app.route('/classes/edit/<int:id>', methods=['GET', 'POST'])
def edit_class(id):
    classroom = db.session.get(ClassRoom, id)
    if not classroom:
        flash('Class not found!')
        return redirect(url_for('list_classes'))
    if request.method == 'POST':
        classroom.name = request.form['name']
        classroom.section = request.form['section']
        classroom.bench_type = request.form.get('bench_type', 'double')
        classroom.row_layout = request.form.get('row_layout')
        classroom.update_capacity()
        
        db.session.commit()
        flash('Class updated successfully!')
        return redirect(url_for('list_classes'))
    return render_template('class_form.html', classroom=classroom, action='Edit')

@app.route('/classes/delete/<int:id>')
def delete_class(id):
    classroom = db.session.get(ClassRoom, id)
    if classroom:
        db.session.delete(classroom)
        db.session.commit()
    flash('Class deleted successfully!')
    return redirect(url_for('list_classes'))

# --- Student CRUD ---
@app.route('/students')
def list_students():
    students = Student.query.all()
    return render_template('students.html', students=students)

@app.route('/students/add', methods=['GET', 'POST'])
def add_student():
    classes = ClassRoom.query.all()
    if request.method == 'POST':
        name = request.form['name']
        roll_number = request.form['roll_number']
        class_id = int(request.form['class_id'])
        new_student = Student(name=name, roll_number=roll_number, class_id=class_id)
        db.session.add(new_student)
        db.session.commit()
        flash('Student added successfully!')
        return redirect(url_for('list_students'))
    return render_template('student_form.html', classes=classes, action='Add')

@app.route('/students/edit/<int:id>', methods=['GET', 'POST'])
def edit_student(id):
    student = db.session.get(Student, id)
    if not student:
        flash('Student not found!')
        return redirect(url_for('list_students'))
    classes = ClassRoom.query.all()
    if request.method == 'POST':
        student.name = request.form['name']
        student.roll_number = request.form['roll_number']
        student.class_id = int(request.form['class_id'])
        db.session.commit()
        flash('Student updated successfully!')
        return redirect(url_for('list_students'))
    return render_template('student_form.html', student=student, classes=classes, action='Edit')

@app.route('/students/delete/<int:id>')
def delete_student(id):
    student = db.session.get(Student, id)
    if student:
        # Delete related seating arrangements first to avoid FK constraints
        SeatingArrangement.query.filter_by(student_id=id).delete()
        db.session.delete(student)
        db.session.commit()
    flash('Student deleted successfully!')
    return redirect(url_for('list_students'))

# --- Supervisor CRUD ---
@app.route('/supervisors')
def list_supervisors():
    supervisors = Supervisor.query.all()
    return render_template('supervisors.html', supervisors=supervisors)

@app.route('/supervisors/add', methods=['GET', 'POST'])
def add_supervisor():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form.get('email')
        phone = request.form.get('phone')
        new_supervisor = Supervisor(name=name, email=email, phone=phone)
        db.session.add(new_supervisor)
        db.session.commit()
        flash('Supervisor added successfully!')
        return redirect(url_for('list_supervisors'))
    return render_template('supervisor_form.html', action='Add')

@app.route('/supervisors/edit/<int:id>', methods=['GET', 'POST'])
def edit_supervisor(id):
    supervisor = db.session.get(Supervisor, id)
    if not supervisor:
        flash('Supervisor not found!')
        return redirect(url_for('list_supervisors'))
    if request.method == 'POST':
        supervisor.name = request.form['name']
        supervisor.email = request.form.get('email')
        supervisor.phone = request.form.get('phone')
        db.session.commit()
        flash('Supervisor updated successfully!')
        return redirect(url_for('list_supervisors'))
    return render_template('supervisor_form.html', supervisor=supervisor, action='Edit')

@app.route('/supervisors/delete/<int:id>')
def delete_supervisor(id):
    supervisor = db.session.get(Supervisor, id)
    if supervisor:
        db.session.delete(supervisor)
        db.session.commit()
    flash('Supervisor deleted successfully!')
    return redirect(url_for('list_supervisors'))

# --- Test CRUD ---
@app.route('/tests')
def list_tests():
    tests = Test.query.all()
    return render_template('tests.html', tests=tests)

@app.route('/tests/add', methods=['GET', 'POST'])
def add_test():
    classes = ClassRoom.query.all()
    supervisors = Supervisor.query.all()
    if request.method == 'POST':
        title = request.form['title']
        paper_sets = request.form['paper_sets']
        duration = int(request.form['duration'])
        date_str = request.form['date']
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        target_classes = request.form.getlist('target_classes')
        
        # Parse blocks: {room_id: supervisor_id}
        exam_blocks = []
        room_ids = request.form.getlist('room_ids')
        for rid in room_ids:
            sid = request.form.get(f'supervisor_{rid}')
            exam_blocks.append({'room_id': int(rid), 'supervisor_id': int(sid) if sid else None})
        
        # Capacity check
        total_students = Student.query.filter(Student.class_id.in_(target_classes)).count()
        total_capacity = 0
        for b in exam_blocks:
            room = db.session.get(ClassRoom, b['room_id'])
            if room:
                total_capacity += room.capacity
            
        if total_students > total_capacity:
            flash(f'Insufficient capacity! Students: {total_students}, Available: {total_capacity}', 'error')
            return redirect(url_for('add_test'))

        new_test = Test(
            title=title, 
            paper_sets=paper_sets,
            duration=duration,
            date=date_obj,
            target_classes_json=json.dumps(target_classes),
            exam_blocks_json=json.dumps(exam_blocks)
        )
        db.session.add(new_test)
        db.session.commit()
        flash('Test created successfully!')
        return redirect(url_for('list_tests'))
    return render_template('test_form.html', classes=classes, supervisors=supervisors, action='Add')

@app.route('/tests/edit/<int:id>', methods=['GET', 'POST'])
def edit_test(id):
    test = db.session.get(Test, id)
    if not test:
        flash('Test not found!')
        return redirect(url_for('list_tests'))
    classes = ClassRoom.query.all()
    supervisors = Supervisor.query.all()
    if request.method == 'POST':
        test.title = request.form['title']
        test.paper_sets = request.form['paper_sets']
        test.duration = int(request.form['duration'])
        date_str = request.form['date']
        test.date = datetime.strptime(date_str, '%Y-%m-%d')
        test.target_classes_json = json.dumps(request.form.getlist('target_classes'))
        
        exam_blocks = []
        room_ids = request.form.getlist('room_ids')
        for rid in room_ids:
            sid = request.form.get(f'supervisor_{rid}')
            exam_blocks.append({'room_id': int(rid), 'supervisor_id': int(sid) if sid else None})
        test.exam_blocks_json = json.dumps(exam_blocks)
        
        db.session.commit()
        flash('Test updated successfully!')
        return redirect(url_for('list_tests'))
    return render_template('test_form.html', test=test, classes=classes, supervisors=supervisors, action='Edit')

@app.route('/tests/delete/<int:id>')
def delete_test(id):
    test = db.session.get(Test, id)
    if test:
        SeatingArrangement.query.filter_by(test_id=id).delete()
        db.session.delete(test)
        db.session.commit()
    flash('Test deleted successfully!')
    return redirect(url_for('list_tests'))

# --- Seating Generation ---
@app.route('/tests/<int:test_id>/generate')
def generate_seating(test_id):
    from utils import generate_seating_plan
    test = db.session.get(Test, test_id)
    if not test:
        flash('Test not found!')
        return redirect(url_for('list_tests'))
    target_class_ids = json.loads(test.target_classes_json)
    blocks = json.loads(test.exam_blocks_json)
    
    room_ids = [b['room_id'] for b in blocks]
    classrooms = ClassRoom.query.filter(ClassRoom.id.in_(room_ids)).all()
    students = Student.query.filter(Student.class_id.in_(target_class_ids)).all()
    
    # Create lookup for supervisor by room
    room_to_supervisor = {b['room_id']: b['supervisor_id'] for b in blocks}
    
    plan, error = generate_seating_plan(test, classrooms, students)
    if error:
        flash(error, 'error')
        return redirect(url_for('list_tests'))
    
    SeatingArrangement.query.filter_by(test_id=test_id).delete()
    for item in plan:
        item['supervisor_id'] = room_to_supervisor.get(item['room_id'])
        arrangement = SeatingArrangement(**item)
        db.session.add(arrangement)
    
    db.session.commit()
    flash('Seating arrangement generated successfully!')
    return redirect(url_for('view_seating', test_id=test_id))

@app.route('/tests/<int:test_id>/seating')
def view_seating(test_id):
    test = db.session.get(Test, test_id)
    if not test:
        flash('Test not found!')
        return redirect(url_for('list_tests'))
    arrangements = SeatingArrangement.query.filter_by(test_id=test_id).all()
    
    # Map seat_number -> arrangement for each room
    room_to_seats = {}
    for arr in arrangements:
        if arr.room_id not in room_to_seats:
            room_to_seats[arr.room_id] = {}
        room_to_seats[arr.room_id][arr.seat_number] = arr
    
    # Build detailed room data using the exam blocks configuration
    blocks = json.loads(test.exam_blocks_json)
    detailed_rooms = []
    for b in blocks:
        room_id = b['room_id']
        room = db.session.get(ClassRoom, room_id)
        if not room: continue
        
        supervisor_id = b['supervisor_id']
        supervisor = db.session.get(Supervisor, supervisor_id) if supervisor_id else None
        
        detailed_rooms.append({
            'room': room,
            'supervisor': supervisor,
            'seats': room_to_seats.get(room_id, {})
        })
    
    return render_template('seating_view.html', test=test, detailed_rooms=detailed_rooms)

@app.route('/tests/<id>/report/teacher')
def report_teacher_copy(id):
    test = db.session.get(Test, id)
    if not test:
        flash('Test not found!')
        return redirect(url_for('list_tests'))
    arrangements = SeatingArrangement.query.filter_by(test_id=id).all()
    
    # Group by room for the grid view
    detailed_rooms = []
    if test.exam_blocks_json:
        blocks = json.loads(test.exam_blocks_json)
        for block in blocks:
            room = db.session.get(ClassRoom, block['room_id'])
            supervisor = db.session.get(Supervisor, block['supervisor_id']) if block.get('supervisor_id') else None
            room_seats = {a.seat_number: a for a in arrangements if a.room_id == room.id}
            
            # Calculate class-wise counts for this specific room
            class_counts = {}
            for seat_num, arr in room_seats.items():
                if arr:
                    class_key = f"{arr.student.classroom.name}-{arr.student.classroom.section}"
                    class_counts[class_key] = class_counts.get(class_key, 0) + 1
            
            detailed_rooms.append({
                'room': room,
                'supervisor': supervisor,
                'seats': room_seats,
                'class_counts': class_counts
            })
            
    return render_template('report_teacher_copy.html', test=test, detailed_rooms=detailed_rooms)

@app.route('/tests/<id>/report/consolidated')
def report_consolidated(id):
    test = db.session.get(Test, id)
    if not test:
        flash('Test not found!')
        return redirect(url_for('list_tests'))
    
    arrangements = SeatingArrangement.query.filter_by(test_id=id).all()
    
    # Get all unique classes involved in this test
    # Get all unique rooms involved in this test (based on arrangements to ensure we only show active blocks)
    active_room_ids = sorted(list(set(a.room_id for a in arrangements)))
    rooms = [db.session.get(ClassRoom, rid) for rid in active_room_ids]
    
    # Get unique class names
    class_names = sorted(list(set(f"{a.student.classroom.name}-{a.student.classroom.section}" for a in arrangements)))
    
    # Matrix: matrix[room_id][class_name] = count
    matrix = {}
    for rid in active_room_ids:
        matrix[rid] = {cname: 0 for cname in class_names}
    
    for a in arrangements:
        class_key = f"{a.student.classroom.name}-{a.student.classroom.section}"
        matrix[a.room_id][class_key] += 1
        
    # Calculate room totals
    room_totals = {rid: sum(matrix[rid].values()) for rid in active_room_ids}
    
    # Calculate class totals
    class_totals = {cname: sum(matrix[rid][cname] for rid in active_room_ids) for cname in class_names}
    
    return render_template('report_consolidated.html', 
                           test=test, 
                           rooms=rooms, 
                           class_names=class_names, 
                           matrix=matrix,
                           room_totals=room_totals,
                           class_totals=class_totals)

@app.route('/tests/<id>/consolidated_export/excel')
def export_consolidated_excel(id):
    test = db.session.get(Test, id)
    if not test: return redirect(url_for('list_tests'))
    arrangements = SeatingArrangement.query.filter_by(test_id=id).all()
    active_room_ids = sorted(list(set(a.room_id for a in arrangements)))
    rooms = [db.session.get(ClassRoom, rid) for rid in active_room_ids]
    class_names = sorted(list(set(f"{a.student.classroom.name}-{a.student.classroom.section}" for a in arrangements)))
    matrix = {rid: {cname: 0 for cname in class_names} for rid in active_room_ids}
    for a in arrangements:
        class_key = f"{a.student.classroom.name}-{a.student.classroom.section}"
        matrix[a.room_id][class_key] += 1
    room_totals = {rid: sum(matrix[rid].values()) for rid in active_room_ids}
    class_totals = {cname: sum(matrix[rid][cname] for rid in active_room_ids) for cname in class_names}
    
    from utils import export_consolidated_excel as excel_func
    output = excel_func(test, rooms, class_names, matrix, room_totals, class_totals)
    return send_file(output, as_attachment=True, download_name=f"Consolidated_Summary_{test.title}.xlsx")

@app.route('/tests/<id>/consolidated_export/pdf')
def export_consolidated_pdf(id):
    test = db.session.get(Test, id)
    if not test: return redirect(url_for('list_tests'))
    arrangements = SeatingArrangement.query.filter_by(test_id=id).all()
    active_room_ids = sorted(list(set(a.room_id for a in arrangements)))
    rooms = [db.session.get(ClassRoom, rid) for rid in active_room_ids]
    class_names = sorted(list(set(f"{a.student.classroom.name}-{a.student.classroom.section}" for a in arrangements)))
    matrix = {rid: {cname: 0 for cname in class_names} for rid in active_room_ids}
    for a in arrangements:
        class_key = f"{a.student.classroom.name}-{a.student.classroom.section}"
        matrix[a.room_id][class_key] += 1
    room_totals = {rid: sum(matrix[rid].values()) for rid in active_room_ids}
    class_totals = {cname: sum(matrix[rid][cname] for rid in active_room_ids) for cname in class_names}
    
    from utils import export_consolidated_pdf as pdf_func
    output = pdf_func(test, rooms, class_names, matrix, room_totals, class_totals)
    return send_file(output, as_attachment=True, download_name=f"Consolidated_Summary_{test.title}.pdf")

@app.route('/tests/<int:test_id>/save_seating', methods=['POST'])
def save_seating(test_id):
    data = request.json
    if not data:
        return {"success": False, "message": "No data received"}, 400
    
    try:
        # data format: [{'student_id': 1, 'room_id': 1, 'seat_number': 1}, ...]
        # For simplicity, we can delete and rebuild the arrangements for this test
        # or update them one by one. Updating one by one is safer for large datasets.
        
        # We need to maintain the supervisor_id and paper_set if it's not being changed by drag-and-drop
        # Actually, if the user moves a student, let's keep the student's paper_set 
        # but change the seat. Wait, the paper_set is tied to the SEAT position in educational apps usually.
        # But here, let's keep it simple: the student MOVES with their data to the new seat.
        
        for item in data:
            arr = SeatingArrangement.query.filter_by(
                test_id=test_id, 
                student_id=item['student_id']
            ).first()
            
            if arr:
                arr.room_id = item['room_id']
                arr.seat_number = item['seat_number']
                if 'paper_set' in item:
                    arr.paper_set = item['paper_set']
                
        db.session.commit()
        return {"success": True}
    except Exception as e:
        db.session.rollback()
        return {"success": False, "message": str(e)}, 500

@app.route('/tests/<int:test_id>/seating/delete/<int:arr_id>', methods=['POST'])
def delete_seating_entry(test_id, arr_id):
    arr = db.session.get(SeatingArrangement, arr_id)
    if arr and arr.test_id == test_id:
        db.session.delete(arr)
        db.session.commit()
        return {"success": True}
    return {"success": False, "message": "Entry not found"}, 404

@app.route('/tests/<int:test_id>/unassigned_students')
def get_unassigned_students(test_id):
    test = db.session.get(Test, test_id)
    if not test: return jsonify([])
    
    target_class_ids = json.loads(test.target_classes_json)
    assigned_student_ids = [a.student_id for a in SeatingArrangement.query.filter_by(test_id=test_id).all()]
    
    unassigned = Student.query.filter(
        Student.class_id.in_(target_class_ids),
        Student.id.notin_(assigned_student_ids)
    ).all()
    
    return jsonify([{
        'id': s.id,
        'name': s.name,
        'roll_number': s.roll_number,
        'class_name': f"{s.classroom.name}-{s.classroom.section}"
    } for s in unassigned])

@app.route('/tests/<int:test_id>/seating/add', methods=['POST'])
def add_seating_entry(test_id):
    data = request.json
    # Expected: {student_id, room_id, seat_number, paper_set}
    new_arr = SeatingArrangement(
        test_id=test_id,
        student_id=data['student_id'],
        room_id=data['room_id'],
        seat_number=data['seat_number'],
        paper_set=data.get('paper_set', 'A')
    )
    # Check if seat already taken
    existing = SeatingArrangement.query.filter_by(
        test_id=test_id,
        room_id=data['room_id'],
        seat_number=data['seat_number']
    ).first()
    if existing:
        return {"success": False, "message": "Seat already occupied"}, 400
        
    db.session.add(new_arr)
    db.session.commit()
    return {"success": True}

@app.route('/tests/<int:test_id>/export/<format>/<type>')
def export_seating(test_id, format, type):
    from utils import export_to_excel, export_to_pdf
    test = db.session.get(Test, test_id)
    if not test:
        flash('Test not found!')
        return redirect(url_for('list_tests'))
    arrangements = SeatingArrangement.query.filter_by(test_id=test_id).all()
    
    if format == 'excel':
        file_data = export_to_excel(test, arrangements, type)
        mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        extension = 'xlsx'
    else:
        file_data = export_to_pdf(test, arrangements, type)
        mimetype = 'application/pdf'
        extension = 'pdf'
        
    return send_file(
        file_data,
        as_attachment=True,
        download_name=f"{test.title}_{type}.{extension}",
        mimetype=mimetype
    )

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
