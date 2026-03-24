from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
import json
import os
import pandas as pd
from io import BytesIO
from datetime import datetime
from firebase_db import get_db
from firebase_admin import auth as firebase_auth
from google.cloud import firestore
from google.cloud.firestore import FieldFilter

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_secret_key')
app.config['UPLOAD_FOLDER'] = 'uploads'

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db = get_db()

# --- Template Filters ---
@app.template_filter('from_json')
def from_json_filter(s):
    if not s: return []
    if isinstance(s, list): return s
    return json.loads(s)

@app.template_filter('room_name')
def room_name_filter(room_id):
    if not room_id: return "Unknown"
    doc = db.collection('classrooms').document(str(room_id)).get()
    if doc.exists:
        room = doc.to_dict()
        return f"{room['name']} - {room['section']}"
    return "Unknown"

@app.template_filter('supervisor_name')
def supervisor_name_filter(supervisor_id):
    if not supervisor_id: return "None"
    doc = db.collection('supervisors').document(str(supervisor_id)).get()
    if doc.exists:
        return doc.to_dict().get('name', 'Unknown')
    return "Unknown"

@app.route('/')
def index():
    stats = {
        'classes': len(db.collection('classrooms').get()),
        'students': len(db.collection('students').get()),
        'tests': len(db.collection('tests').get()),
        'supervisors': len(db.collection('supervisors').get())
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
                
                count = 0
                errors = []
                
                if import_type == 'classes':
                    for _, row in df.iterrows():
                        name = str(row.get('Name', ''))
                        section = str(row.get('Section', ''))
                        capacity = int(row.get('Capacity', 0))
                        if name and section:
                            db.collection('classrooms').add({
                                'name': name,
                                'section': section,
                                'capacity': capacity,
                                'rows': 5,
                                'columns': (capacity // 10) or 4,
                                'bench_type': 'double',
                                'row_layout': None
                            })
                            count += 1
                elif import_type == 'students':
                    for _, row in df.iterrows():
                        cls_str = str(row.get('Class', '')).strip()
                        if '-' in cls_str:
                            cls_name, cls_sec = cls_str.split('-', 1)
                        elif ' ' in cls_str:
                            cls_name, cls_sec = cls_str.split(' ', 1)
                        else:
                            errors.append(f"Invalid class format for student {row.get('Name')}: {cls_str}. Expected format: 'X-A' or 'X A'")
                            continue
                            
                        query = db.collection('classrooms').where(filter=FieldFilter('name', '==', cls_name.strip())).where(filter=FieldFilter('section', '==', cls_sec.strip())).get()
                        if query:
                            classroom_id = query[0].id
                            db.collection('students').add({
                                'name': str(row.get('Name', '')),
                                'roll_number': str(row.get('Roll Number', '')),
                                'classroom_id': str(classroom_id)
                            })
                            count += 1
                        else:
                            errors.append(f"Class '{cls_name.strip()}-{cls_sec.strip()}' not found in database for student {row.get('Name')}")
                elif import_type == 'supervisors':
                    for _, row in df.iterrows():
                        name = str(row.get('Name', ''))
                        email = str(row.get('Email', ''))
                        phone = str(row.get('Phone', ''))
                        if name:
                            db.collection('supervisors').add({
                                'name': name,
                                'email': email,
                                'phone': phone
                            })
                            count += 1
                
                msg = f'Imported {count} {import_type} successfully!'
                if errors:
                    msg += f' Skipped {len(errors)} rows due to errors.'
                    for err in errors[:5]: # Show first 5 errors
                        flash(err, 'warning')
                flash(msg, 'success')
            except Exception as e:
                flash(f'Error importing: {str(e)}', 'error')
            return redirect(url_for('index'))
    return render_template('import.html')

@app.route('/import/template/<type>')
def download_template(type):
    output = BytesIO()
    if type == 'classes':
        df = pd.DataFrame(columns=['Name', 'Section', 'Capacity'])
    elif type == 'students':
        df = pd.DataFrame(columns=['Name', 'Roll Number', 'Class']) # Class as Grade 10-A
    elif type == 'supervisors':
        df = pd.DataFrame(columns=['Name', 'Email', 'Phone'])
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name=f'{type}_template.xlsx')

# --- Class CRUD ---
@app.route('/classes')
def list_classes():
    classes = [doc.to_dict() | {'id': doc.id} for doc in db.collection('classrooms').get()]
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
        
        # Calculate capacity
        layout = [int(x.strip()) for x in row_layout.split(',')] if row_layout else [columns] * rows
        multiplier = 1 if bench_type == 'single' else 2
        capacity = sum(layout) * multiplier
        
        new_class = {
            'name': name, 
            'section': section, 
            'rows': len(layout),
            'columns': max(layout) if layout else 0,
            'bench_type': bench_type, 
            'row_layout': row_layout,
            'capacity': capacity
        }
        db.collection('classrooms').add(new_class)
        flash('Class added successfully!')
        return redirect(url_for('list_classes'))
    return render_template('class_form.html', action='Add')

@app.route('/classes/edit/<id>', methods=['GET', 'POST'])
def edit_class(id):
    doc_ref = db.collection('classrooms').document(str(id))
    doc = doc_ref.get()
    if not doc.exists:
        flash('Class not found!')
        return redirect(url_for('list_classes'))
    
    classroom = doc.to_dict() | {'id': doc.id}
    # Augment dictionary with method for template
    def get_row_layout_dict(self):
        if not self.get('row_layout'): return [self.get('columns', 4)] * self.get('rows', 5)
        return [int(x.strip()) for x in self['row_layout'].split(',')]
    classroom['get_row_layout'] = get_row_layout_dict.__get__(classroom)

    if request.method == 'POST':
        name = request.form['name']
        section = request.form['section']
        bench_type = request.form.get('bench_type', 'double')
        row_layout = request.form.get('row_layout')
        
        layout = [int(x.strip()) for x in row_layout.split(',')] if row_layout else [int(classroom.get('columns', 4))] * int(classroom.get('rows', 5))
        multiplier = 1 if bench_type == 'single' else 2
        capacity = sum(layout) * multiplier
        
        doc_ref.update({
            'name': name,
            'section': section,
            'bench_type': bench_type,
            'row_layout': row_layout,
            'rows': len(layout),
            'columns': max(layout) if layout else 0,
            'capacity': capacity
        })
        flash('Class updated successfully!')
        return redirect(url_for('list_classes'))
    return render_template('class_form.html', classroom=classroom, action='Edit')

@app.route('/classes/delete/<id>')
def delete_class(id):
    db.collection('classrooms').document(str(id)).delete()
    flash('Class deleted successfully!')
    return redirect(url_for('list_classes'))

# --- Student CRUD ---
@app.route('/students')
def list_students():
    # We need to include classroom info for display
    students = []
    for doc in db.collection('students').get():
        s = doc.to_dict() | {'id': doc.id}
        # Fetch classroom data
        c_doc = db.collection('classrooms').document(str(s['classroom_id'])).get()
        if c_doc.exists:
            c = c_doc.to_dict()
            class_obj = type('obj', (object,), {'name': c['name'], 'section': c['section']})
            s['classroom'] = class_obj
        students.append(s)
    return render_template('students.html', students=students)

@app.route('/students/add', methods=['GET', 'POST'])
def add_student():
    classes = [doc.to_dict() | {'id': doc.id} for doc in db.collection('classrooms').get()]
    if request.method == 'POST':
        name = request.form['name']
        roll_number = request.form['roll_number']
        classroom_id = request.form['class_id']
        db.collection('students').add({
            'name': name,
            'roll_number': roll_number,
            'classroom_id': str(classroom_id)
        })
        flash('Student added successfully!')
        return redirect(url_for('list_students'))
    return render_template('student_form.html', classes=classes, action='Add')

@app.route('/students/edit/<id>', methods=['GET', 'POST'])
def edit_student(id):
    doc_ref = db.collection('students').document(str(id))
    doc = doc_ref.get()
    if not doc.exists:
        flash('Student not found!')
        return redirect(url_for('list_students'))
    
    student = doc.to_dict() | {'id': doc.id}
    classes = [c_doc.to_dict() | {'id': c_doc.id} for c_doc in db.collection('classrooms').get()]
    
    if request.method == 'POST':
        doc_ref.update({
            'name': request.form['name'],
            'roll_number': request.form['roll_number'],
            'classroom_id': str(request.form['class_id'])
        })
        flash('Student updated successfully!')
        return redirect(url_for('list_students'))
    return render_template('student_form.html', student=student, classes=classes, action='Edit')

@app.route('/students/delete/<id>')
def delete_student(id):
    # Delete related seating arrangements first
    arrangements = db.collection('seating_arrangements').where(filter=FieldFilter('student_id', '==', str(id))).get()
    for doc in arrangements:
        doc.reference.delete()
    
    db.collection('students').document(str(id)).delete()
    flash('Student deleted successfully!')
    return redirect(url_for('list_students'))

# --- Supervisor CRUD ---
@app.route('/supervisors')
def list_supervisors():
    supervisors = [doc.to_dict() | {'id': doc.id} for doc in db.collection('supervisors').get()]
    return render_template('supervisors.html', supervisors=supervisors)

@app.route('/supervisors/add', methods=['GET', 'POST'])
def add_supervisor():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone')
        password = request.form.get('password')
        
        sup_data = {
            'name': name,
            'email': email,
            'phone': phone
        }
        
        # Create Firebase Auth account if email and password provided
        if email and password:
            try:
                user = firebase_auth.create_user(email=email, password=password, display_name=name)
                sup_data['auth_uid'] = user.uid
                flash(f'Mobile login account created for {email}', 'success')
            except firebase_auth.EmailAlreadyExistsError:
                # User exists, update password
                try:
                    existing = firebase_auth.get_user_by_email(email)
                    firebase_auth.update_user(existing.uid, password=password)
                    sup_data['auth_uid'] = existing.uid
                    flash(f'Password updated for {email}', 'success')
                except Exception as e:
                    flash(f'Auth error: {str(e)}', 'warning')
            except Exception as e:
                flash(f'Could not create login: {str(e)}', 'warning')
        
        db.collection('supervisors').add(sup_data)
        flash('Supervisor added successfully!')
        return redirect(url_for('list_supervisors'))
    return render_template('supervisor_form.html', action='Add')

@app.route('/supervisors/edit/<id>', methods=['GET', 'POST'])
def edit_supervisor(id):
    doc_ref = db.collection('supervisors').document(str(id))
    doc = doc_ref.get()
    if not doc.exists:
        flash('Supervisor not found!')
        return redirect(url_for('list_supervisors'))
    
    supervisor = doc.to_dict() | {'id': doc.id}
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        
        update_data = {
            'name': request.form['name'],
            'email': email,
            'phone': request.form.get('phone')
        }
        
        # Handle Firebase Auth account
        if email and password:
            try:
                existing = firebase_auth.get_user_by_email(email)
                firebase_auth.update_user(existing.uid, password=password, display_name=request.form['name'])
                update_data['auth_uid'] = existing.uid
                flash(f'Password updated for {email}', 'success')
            except firebase_auth.UserNotFoundError:
                try:
                    user = firebase_auth.create_user(email=email, password=password, display_name=request.form['name'])
                    update_data['auth_uid'] = user.uid
                    flash(f'Mobile login account created for {email}', 'success')
                except Exception as e:
                    flash(f'Auth error: {str(e)}', 'warning')
            except Exception as e:
                flash(f'Auth error: {str(e)}', 'warning')
        
        doc_ref.update(update_data)
        flash('Supervisor updated successfully!')
        return redirect(url_for('list_supervisors'))
    return render_template('supervisor_form.html', supervisor=supervisor, action='Edit')

@app.route('/supervisors/delete/<id>')
def delete_supervisor(id):
    db.collection('supervisors').document(str(id)).delete()
    flash('Supervisor deleted successfully!')
    return redirect(url_for('list_supervisors'))

@app.route('/supervisors/reports')
def supervision_reports():
    year = request.args.get('year', datetime.now().year, type=int)
    all_tests = db.collection('tests').get()
    supervisors = {doc.id: doc.to_dict() | {'id': doc.id, 'count': 0} for doc in db.collection('supervisors').get()}
    
    for t_doc in all_tests:
        t = t_doc.to_dict()
        if t.get('date') and t['date'].year == year:
            blocks = t.get('exam_blocks', [])
            for b in blocks:
                sid = b.get('supervisor_id')
                if sid in supervisors:
                    supervisors[sid]['count'] += 1
                    
    # Sort by count descending
    sorted_supervisors = sorted(supervisors.values(), key=lambda x: x['count'], reverse=True)
    return render_template('reports_supervision.html', supervisors=sorted_supervisors, current_year=year)

@app.route('/supervisors/report/<id>')
def supervisor_detail_report(id):
    s_doc = db.collection('supervisors').document(str(id)).get()
    if not s_doc.exists:
        flash('Supervisor not found!')
        return redirect(url_for('supervision_reports'))
    
    supervisor = s_doc.to_dict() | {'id': s_doc.id}
    history = []
    all_tests = db.collection('tests').order_by('date', direction=firestore.Query.DESCENDING).get()
    
    for t_doc in all_tests:
        t = t_doc.to_dict() | {'id': t_doc.id}
        blocks = t.get('exam_blocks', [])
        for b in blocks:
            if b.get('supervisor_id') == str(id):
                # Get room info
                r_doc = db.collection('classrooms').document(str(b['room_id'])).get()
                room = r_doc.to_dict() if r_doc.exists else {'name': 'Unknown', 'section': ''}
                history.append({
                    'test_title': t['title'],
                    'date': t['date'],
                    'room_name': f"{room.get('name')} {room.get('section')}".strip()
                })
                
    return render_template('report_supervisor_detail.html', supervisor=supervisor, history=history)

# --- Test CRUD ---
@app.route('/tests')
def list_tests():
    tests = []
    for doc in db.collection('tests').get():
        t = doc.to_dict() | {'id': doc.id}
        # Check if seating has been generated
        arr_count = len(db.collection('seating_arrangements').where(filter=FieldFilter('test_id', '==', doc.id)).get())
        t['arrangements'] = [0] * arr_count # Create a dummy list of the right length for the template
        tests.append(t)
    return render_template('tests.html', tests=tests)

@app.route('/tests/add', methods=['GET', 'POST'])
def add_test():
    classes = []
    for doc in db.collection('classrooms').get():
        c = doc.to_dict() | {'id': doc.id}
        # Add student count for this class
        s_count = len(db.collection('students').where(filter=FieldFilter('classroom_id', '==', doc.id)).get())
        c['student_count'] = s_count
        classes.append(c)
        
    supervisors = [doc.to_dict() | {'id': doc.id} for doc in db.collection('supervisors').get()]
    
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
            exam_blocks.append({'room_id': str(rid), 'supervisor_id': str(sid) if sid else None})
        
        # Capacity check
        total_students = 0
        for cid in target_classes:
            total_students += len(db.collection('students').where(filter=FieldFilter('classroom_id', '==', str(cid))).get())
            
        total_capacity = 0
        for b in exam_blocks:
            r_doc = db.collection('classrooms').document(str(b['room_id'])).get()
            if r_doc.exists:
                total_capacity += r_doc.to_dict().get('capacity', 0)
            
        if total_students > total_capacity:
            flash(f'Insufficient capacity! Students: {total_students}, Available: {total_capacity}', 'error')
            return redirect(url_for('add_test'))

        db.collection('tests').add({
            'title': title, 
            'paper_sets': paper_sets,
            'duration': duration,
            'date': date_obj,
            'target_classes': target_classes,
            'exam_blocks': exam_blocks
        })
        flash('Test created successfully!')
        return redirect(url_for('list_tests'))
    return render_template('test_form.html', classes=classes, supervisors=supervisors, action='Add')

@app.route('/tests/edit/<id>', methods=['GET', 'POST'])
def edit_test(id):
    doc_ref = db.collection('tests').document(str(id))
    doc = doc_ref.get()
    if not doc.exists:
        flash('Test not found!')
        return redirect(url_for('list_tests'))
    
    test = doc.to_dict() | {'id': doc.id}
    classes = []
    for c_doc in db.collection('classrooms').get():
        c = c_doc.to_dict() | {'id': c_doc.id}
        s_count = len(db.collection('students').where(filter=FieldFilter('classroom_id', '==', c_doc.id)).get())
        c['student_count'] = s_count
        classes.append(c)
        
    supervisors = [s_doc.to_dict() | {'id': s_doc.id} for s_doc in db.collection('supervisors').get()]
    
    if request.method == 'POST':
        date_str = request.form['date']
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        
        exam_blocks = []
        room_ids = request.form.getlist('room_ids')
        for rid in room_ids:
            sid = request.form.get(f'supervisor_{rid}')
            exam_blocks.append({'room_id': str(rid), 'supervisor_id': str(sid) if sid else None})
            
        doc_ref.update({
            'title': request.form['title'],
            'paper_sets': request.form['paper_sets'],
            'duration': int(request.form['duration']),
            'date': date_obj,
            'target_classes': request.form.getlist('target_classes'),
            'exam_blocks': exam_blocks
        })
        flash('Test updated successfully!')
        return redirect(url_for('list_tests'))
    return render_template('test_form.html', test=test, classes=classes, supervisors=supervisors, action='Edit')

@app.route('/tests/delete/<id>')
def delete_test(id):
    # Delete related seating arrangements
    arrs = db.collection('seating_arrangements').where(filter=FieldFilter('test_id', '==', str(id))).get()
    for doc in arrs:
        doc.reference.delete()
        
    db.collection('tests').document(str(id)).delete()
    flash('Test deleted successfully!')
    return redirect(url_for('list_tests'))

# --- Seating Generation ---
@app.route('/tests/<test_id>/generate')
def generate_seating(test_id):
    from utils import generate_seating_plan
    doc = db.collection('tests').document(str(test_id)).get()
    if not doc.exists:
        flash('Test not found!')
        return redirect(url_for('list_tests'))
    
    test_data = doc.to_dict() | {'id': doc.id}
    # Algorithm expects a 'paper_sets' string and object-like access for 'id'
    test_obj = type('obj', (object,), test_data)
    
    target_class_ids = test_data.get('target_classes', [])
    blocks = test_data.get('exam_blocks', [])
    
    room_ids = [b['room_id'] for b in blocks]
    
    # Fetch classrooms and students
    classrooms = []
    for rid in room_ids:
        r_doc = db.collection('classrooms').document(str(rid)).get()
        if r_doc.exists:
            # Algorithm expects classroom.get_row_layout() and classroom.id/bench_type/etc.
            c_data = r_doc.to_dict() | {'id': r_doc.id}
            
            def get_row_layout(self):
                if not self.row_layout: return [self.columns] * self.rows
                return [int(x.strip()) for x in self.row_layout.split(',')]
            
            c_obj = type('obj', (object,), c_data)
            c_obj.get_row_layout = get_row_layout.__get__(c_obj)
            classrooms.append(c_obj)
            
    students = []
    for cid in target_class_ids:
        s_docs = db.collection('students').where(filter=FieldFilter('classroom_id', '==', str(cid))).get()
        for s_doc in s_docs:
            s_data = s_doc.to_dict() | {'id': s_doc.id}
            # Algorithm expects student.id, student.classroom.name/section
            c_lookup = db.collection('classrooms').document(str(s_data['classroom_id'])).get().to_dict()
            s_data['classroom'] = type('obj', (object,), c_lookup)
            students.append(type('obj', (object,), s_data))
    
    # Create lookup for supervisor by room
    room_to_supervisor = {b['room_id']: b['supervisor_id'] for b in blocks}
    
    plan, error = generate_seating_plan(test_obj, classrooms, students)
    if error:
        flash(error, 'error')
        return redirect(url_for('list_tests'))
    
    # Delete old arrangements
    old_arrs = db.collection('seating_arrangements').where(filter=FieldFilter('test_id', '==', str(test_id))).get()
    for old_arr in old_arrs:
        old_arr.reference.delete()
        
    for item in plan:
        item['test_id'] = str(test_id)
        item['room_id'] = str(item['room_id'])
        item['student_id'] = str(item['student_id'])
        item['supervisor_id'] = str(room_to_supervisor.get(str(item['room_id']))) if room_to_supervisor.get(str(item['room_id'])) else None
        db.collection('seating_arrangements').add(item)
    
    flash('Seating arrangement generated successfully!')
    return redirect(url_for('view_seating', test_id=test_id))

@app.route('/tests/<test_id>/seating')
def view_seating(test_id):
    doc = db.collection('tests').document(str(test_id)).get()
    if not doc.exists:
        flash('Test not found!')
        return redirect(url_for('list_tests'))
    
    test = doc.to_dict() | {'id': doc.id}
    arrangements_docs = db.collection('seating_arrangements').where(filter=FieldFilter('test_id', '==', str(test_id))).get()
    
    # seat_number -> arrangement
    room_to_seats = {}
    for a_doc in arrangements_docs:
        a = a_doc.to_dict() | {'id': a_doc.id}
        rid = a['room_id']
        if rid not in room_to_seats: room_to_seats[rid] = {}
        
        # Need student info for badges
        s_doc = db.collection('students').document(str(a['student_id'])).get()
        if s_doc.exists:
            s = s_doc.to_dict() | {'id': s_doc.id}
            c_doc = db.collection('classrooms').document(str(s['classroom_id'])).get()
            s['classroom'] = (c_doc.to_dict() | {'id': c_doc.id}) if c_doc.exists else {}
            a['student'] = s
            
        room_to_seats[rid][a['seat_number']] = a
    
    # Fetch target classes for side-by-side filtering/downloads
    target_class_ids = test.get('target_classes', [])
    test_classes = []
    for cid in target_class_ids:
        c_doc = db.collection('classrooms').document(str(cid)).get()
        if c_doc.exists:
            test_classes.append(c_doc.to_dict() | {'id': c_doc.id})
    
    blocks = test.get('exam_blocks', [])
    detailed_rooms = []
    for b in blocks:
        room_id = b['room_id']
        r_doc = db.collection('classrooms').document(str(room_id)).get()
        if not r_doc.exists: continue
        
        room = r_doc.to_dict() | {'id': r_doc.id}
        
        # Method for template
        def get_row_layout(self):
            if not self.get('row_layout'): return [self.get('columns', 4)] * self.get('rows', 5)
            return [int(x.strip()) for x in self['row_layout'].split(',')]
        room['get_row_layout'] = get_row_layout.__get__(room)

        sid = b.get('supervisor_id')
        supervisor = None
        if sid:
            s_doc = db.collection('supervisors').document(str(sid)).get()
            if s_doc.exists: supervisor = s_doc.to_dict() | {'id': s_doc.id}
        
        detailed_rooms.append({
            'room': room,
            'supervisor': supervisor,
            'seats': room_to_seats.get(str(room_id), {})
        })
    
    return render_template('seating_view.html', test=test, detailed_rooms=detailed_rooms, test_classes=test_classes)

@app.route('/tests/<id>/report/teacher')
def report_teacher_copy(id):
    doc = db.collection('tests').document(str(id)).get()
    if not doc.exists:
        flash('Test not found!')
        return redirect(url_for('list_tests'))
    
    test = doc.to_dict() | {'id': doc.id}
    arrangements_docs = db.collection('seating_arrangements').where(filter=FieldFilter('test_id', '==', str(id))).get()
    arrangements = [a.to_dict() | {'id': a.id} for a in arrangements_docs]
    
    # Pre-fetch students to avoid N+1
    students_lookup = {}
    for a in arrangements:
        s_id = a['student_id']
        if s_id not in students_lookup:
            s_doc = db.collection('students').document(str(s_id)).get()
            if s_doc.exists:
                s_data = s_doc.to_dict() | {'id': s_doc.id}
                c_doc = db.collection('classrooms').document(str(s_data['classroom_id'])).get()
                s_data['classroom'] = (c_doc.to_dict() | {'id': c_doc.id}) if c_doc.exists else {}
                students_lookup[s_id] = type('obj', (object,), s_data)
        a['student'] = students_lookup.get(s_id)

    detailed_rooms = []
    blocks = test.get('exam_blocks', [])
    for block in blocks:
        r_id = block['room_id']
        r_doc = db.collection('classrooms').document(str(r_id)).get()
        if not r_doc.exists: continue
        
        room = r_doc.to_dict() | {'id': r_doc.id}
        s_id = block.get('supervisor_id')
        supervisor = None
        if s_id:
            s_doc = db.collection('supervisors').document(str(s_id)).get()
            if s_doc.exists: supervisor = s_doc.to_dict() | {'id': s_doc.id}
            
        room_seats = {a['seat_number']: type('obj', (object,), a) for a in arrangements if a['room_id'] == str(r_id)}
        
        class_counts = {}
        for seat_num, arr in room_seats.items():
            if arr and hasattr(arr.student, 'classroom'):
                class_key = f"{arr.student.classroom.get('name')}-{arr.student.classroom.get('section')}"
                class_counts[class_key] = class_counts.get(class_key, 0) + 1
        
        room_obj = type('obj', (object,), room)
        def get_row_layout_report(self):
            if not getattr(self, 'row_layout', None): return [getattr(self, 'columns', 4)] * getattr(self, 'rows', 5)
            return [int(x.strip()) for x in self.row_layout.split(',')]
        room_obj.get_row_layout = get_row_layout_report.__get__(room_obj)
        
        detailed_rooms.append({
            'room': room_obj,
            'supervisor': supervisor,
            'seats': room_seats,
            'class_counts': class_counts
        })
            
    return render_template('report_teacher_copy.html', test=test, detailed_rooms=detailed_rooms)

@app.route('/tests/<id>/report/consolidated')
def report_consolidated(id):
    doc = db.collection('tests').document(str(id)).get()
    if not doc.exists:
        flash('Test not found!')
        return redirect(url_for('list_tests'))
    
    test = doc.to_dict() | {'id': doc.id}
    arrangements_docs = db.collection('seating_arrangements').where(filter=FieldFilter('test_id', '==', str(id))).get()
    
    # Rebuild logic with pre-fetched rooms and students
    arrangements = []
    for a_doc in arrangements_docs:
        a = a_doc.to_dict() | {'id': a_doc.id}
        s_doc = db.collection('students').document(str(a['student_id'])).get()
        if s_doc.exists:
            s_data = s_doc.to_dict() | {'id': s_doc.id}
            c_doc = db.collection('classrooms').document(str(s_data['classroom_id'])).get()
            s_data['classroom'] = (c_doc.to_dict() | {'id': c_doc.id}) if c_doc.exists else {}
            a['student'] = type('obj', (object,), s_data)
            a['student'].classroom = type('obj', (object,), s_data['classroom'])
            arrangements.append(type('obj', (object,), a))

    active_room_ids = sorted(list(set(str(a.room_id) for a in arrangements)))
    rooms = []
    for rid in active_room_ids:
        r_doc = db.collection('classrooms').document(str(rid)).get()
        if r_doc.exists: rooms.append(type('obj', (object,), r_doc.to_dict() | {'id': r_doc.id}))
    
    class_names = sorted(list(set(f"{a.student.classroom.name}-{a.student.classroom.section}" for a in arrangements)))
    
    matrix = {rid: {cname: {'total': 0, 'sets': {}} for cname in class_names} for rid in active_room_ids}
    for a in arrangements:
        class_key = f"{a.student.classroom.name}-{a.student.classroom.section}"
        p_set = getattr(a, 'paper_set', 'A')
        matrix[str(a.room_id)][class_key]['total'] += 1
        matrix[str(a.room_id)][class_key]['sets'][p_set] = matrix[str(a.room_id)][class_key]['sets'].get(p_set, 0) + 1
        
    room_totals = {rid: sum(matrix[rid][cname]['total'] for cname in class_names) for rid in active_room_ids}
    class_totals = {cname: sum(matrix[rid][cname]['total'] for rid in active_room_ids) for cname in class_names}
    
    return render_template('report_consolidated.html', 
                           test=test, rooms=rooms, class_names=class_names, 
                           matrix=matrix, room_totals=room_totals, class_totals=class_totals)

@app.route('/tests/<id>/consolidated_export/excel')
def export_consolidated_excel(id):
    doc = db.collection('tests').document(str(id)).get()
    if not doc.exists: return redirect(url_for('list_tests'))
    test_data = doc.to_dict() | {'id': doc.id}
    test = type('obj', (object,), test_data)

    arrangements_docs = db.collection('seating_arrangements').where(filter=FieldFilter('test_id', '==', str(id))).get()
    arrangements = []
    for a_doc in arrangements_docs:
        a = a_doc.to_dict() | {'id': a_doc.id}
        s_doc = db.collection('students').document(str(a['student_id'])).get()
        if s_doc.exists:
            s_data = s_doc.to_dict() | {'id': s_doc.id}
            c_doc = db.collection('classrooms').document(str(s_data['classroom_id'])).get()
            s_data['classroom'] = (c_doc.to_dict() | {'id': c_doc.id}) if c_doc.exists else {}
            a['student'] = type('obj', (object,), s_data)
            a['student'].classroom = type('obj', (object,), s_data['classroom'])
            arrangements.append(type('obj', (object,), a))

    active_room_ids = sorted(list(set(str(a.room_id) for a in arrangements)))
    rooms = []
    for rid in active_room_ids:
        r_doc = db.collection('classrooms').document(str(rid)).get()
        if r_doc.exists: rooms.append(type('obj', (object,), r_doc.to_dict() | {'id': r_doc.id}))
        
    class_names = sorted(list(set(f"{a.student.classroom.name}-{a.student.classroom.section}" for a in arrangements)))
    matrix = {rid: {cname: {'total': 0, 'sets': {}} for cname in class_names} for rid in active_room_ids}
    for a in arrangements:
        class_key = f"{a.student.classroom.name}-{a.student.classroom.section}"
        p_set = getattr(a, 'paper_set', 'A')
        matrix[str(a.room_id)][class_key]['total'] += 1
        matrix[str(a.room_id)][class_key]['sets'][p_set] = matrix[str(a.room_id)][class_key]['sets'].get(p_set, 0) + 1
        
    room_totals = {rid: sum(matrix[rid][cname]['total'] for cname in class_names) for rid in active_room_ids}
    class_totals = {cname: sum(matrix[rid][cname]['total'] for rid in active_room_ids) for cname in class_names}
    
    from utils import export_consolidated_excel as excel_func
    output = excel_func(test, rooms, class_names, matrix, room_totals, class_totals)
    return send_file(output, as_attachment=True, download_name=f"Consolidated_Summary_{test.title}.xlsx")

@app.route('/tests/<id>/consolidated_export/pdf')
def export_consolidated_pdf(id):
    doc = db.collection('tests').document(str(id)).get()
    if not doc.exists: return redirect(url_for('list_tests'))
    test_data = doc.to_dict() | {'id': doc.id}
    test = type('obj', (object,), test_data)

    arrangements_docs = db.collection('seating_arrangements').where(filter=FieldFilter('test_id', '==', str(id))).get()
    arrangements = []
    for a_doc in arrangements_docs:
        a = a_doc.to_dict() | {'id': a_doc.id}
        s_doc = db.collection('students').document(str(a['student_id'])).get()
        if s_doc.exists:
            s_data = s_doc.to_dict() | {'id': s_doc.id}
            c_doc = db.collection('classrooms').document(str(s_data['classroom_id'])).get()
            s_data['classroom'] = (c_doc.to_dict() | {'id': c_doc.id}) if c_doc.exists else {}
            a['student'] = type('obj', (object,), s_data)
            a['student'].classroom = type('obj', (object,), s_data['classroom'])
            arrangements.append(type('obj', (object,), a))

    active_room_ids = sorted(list(set(str(a.room_id) for a in arrangements)))
    rooms = []
    for rid in active_room_ids:
        r_doc = db.collection('classrooms').document(str(rid)).get()
        if r_doc.exists: rooms.append(type('obj', (object,), r_doc.to_dict() | {'id': r_doc.id}))
        
    class_names = sorted(list(set(f"{a.student.classroom.name}-{a.student.classroom.section}" for a in arrangements)))
    matrix = {rid: {cname: {'total': 0, 'sets': {}} for cname in class_names} for rid in active_room_ids}
    for a in arrangements:
        class_key = f"{a.student.classroom.name}-{a.student.classroom.section}"
        p_set = getattr(a, 'paper_set', 'A')
        matrix[str(a.room_id)][class_key]['total'] += 1
        matrix[str(a.room_id)][class_key]['sets'][p_set] = matrix[str(a.room_id)][class_key]['sets'].get(p_set, 0) + 1
    room_totals = {rid: sum(matrix[rid][cname]['total'] for cname in class_names) for rid in active_room_ids}
    class_totals = {cname: sum(matrix[rid][cname]['total'] for rid in active_room_ids) for cname in class_names}
    
    from utils import export_consolidated_pdf as pdf_func
    output = pdf_func(test, rooms, class_names, matrix, room_totals, class_totals)
    return send_file(output, as_attachment=True, download_name=f"Consolidated_Summary_{test.title}.pdf")

@app.route('/tests/<test_id>/save_seating', methods=['POST'])
def save_seating(test_id):
    data = request.json
    if not data:
        return {"success": False, "message": "No data received"}, 400
    
    try:
        for item in data:
            # Find the arrangement for this student in this test
            query = db.collection('seating_arrangements')\
                .where(filter=FieldFilter('test_id', '==', str(test_id)))\
                .where(filter=FieldFilter('student_id', '==', str(item['student_id'])))\
                .get()
            
            if query:
                doc_ref = query[0].reference
                update_data = {
                    'room_id': str(item['room_id']),
                    'seat_number': int(item['seat_number'])
                }
                if 'paper_set' in item:
                    update_data['paper_set'] = item['paper_set']
                doc_ref.update(update_data)
                
        return {"success": True}
    except Exception as e:
        return {"success": False, "message": str(e)}, 500

@app.route('/tests/<test_id>/seating/delete/<arr_id>', methods=['POST'])
def delete_seating_entry(test_id, arr_id):
    doc_ref = db.collection('seating_arrangements').document(str(arr_id))
    doc = doc_ref.get()
    if doc.exists and doc.to_dict().get('test_id') == str(test_id):
        doc_ref.delete()
        return {"success": True}
    return {"success": False, "message": "Entry not found"}, 404

@app.route('/tests/<test_id>/unassigned_students')
def get_unassigned_students(test_id):
    doc = db.collection('tests').document(str(test_id)).get()
    if not doc.exists: return jsonify([])
    
    test = doc.to_dict()
    target_class_ids = test.get('target_classes', [])
    
    # Get assigned students
    assigned_docs = db.collection('seating_arrangements').where(filter=FieldFilter('test_id', '==', str(test_id))).get()
    assigned_student_ids = set(str(a.to_dict().get('student_id')) for a in assigned_docs)
    
    unassigned = []
    # Pre-fetch classroom names to avoid repeated lookups
    classroom_names = {}
    for cid in target_class_ids:
        c_doc = db.collection('classrooms').document(str(cid)).get()
        if c_doc.exists:
            c = c_doc.to_dict()
            classroom_names[cid] = f"{c.get('name')}-{c.get('section')}"

    for cid in target_class_ids:
        s_docs = db.collection('students').where('classroom_id', '==', str(cid)).get()
        for s_doc in s_docs:
            if s_doc.id not in assigned_student_ids:
                s = s_doc.to_dict()
                unassigned.append({
                    'id': s_doc.id,
                    'name': s['name'],
                    'roll_number': s.get('roll_number', 'N/A'),
                    'class_name': classroom_names.get(cid, 'N/A')
                })
                
    return jsonify(unassigned)

@app.route('/tests/<test_id>/seating/add', methods=['POST'])
def add_seating_entry(test_id):
    data = request.json
    # Check if seat already taken
    existing = db.collection('seating_arrangements')\
        .where(filter=FieldFilter('test_id', '==', str(test_id)))\
        .where(filter=FieldFilter('room_id', '==', str(data['room_id'])))\
        .where(filter=FieldFilter('seat_number', '==', int(data['seat_number'])))\
        .get()
        
    if existing:
        return {"success": False, "message": "Seat already occupied"}, 400
        
    db.collection('seating_arrangements').add({
        'test_id': str(test_id),
        'student_id': str(data['student_id']),
        'room_id': str(data['room_id']),
        'seat_number': int(data['seat_number']),
        'paper_set': data.get('paper_set', 'A')
    })
    return {"success": True}

# --- Attendance View ---
@app.route('/tests/<id>/attendance')
def view_attendance(id):
    doc = db.collection('tests').document(str(id)).get()
    if not doc.exists:
        flash('Test not found!')
        return redirect(url_for('list_tests'))
    
    test = doc.to_dict() | {'id': doc.id}
    
    # Get all attendance records for this test
    att_docs = db.collection('attendance').where(filter=FieldFilter('test_id', '==', str(id))).get()
    attendance_records = [a.to_dict() | {'id': a.id} for a in att_docs]
    
    # Get all seating arrangements to show who hasn't been marked
    arrs = db.collection('seating_arrangements').where(filter=FieldFilter('test_id', '==', str(id))).get()
    
    # Build a lookup of student details
    all_students = {}
    rooms_lookup = {}
    for a_doc in arrs:
        a = a_doc.to_dict()
        s_id = a['student_id']
        r_id = a['room_id']
        
        if s_id not in all_students:
            s_doc = db.collection('students').document(str(s_id)).get()
            if s_doc.exists:
                s_data = s_doc.to_dict() | {'id': s_doc.id}
                c_doc = db.collection('classrooms').document(str(s_data.get('classroom_id', ''))).get()
                c_name = f"{(c_doc.to_dict() | {'id': c_doc.id})['name'] if c_doc.exists else 'Unknown'}-{(c_doc.to_dict() | {'id': c_doc.id})['section'] if c_doc.exists else ''}"
                all_students[s_id] = {
                    'name': s_data.get('name', 'Unknown'),
                    'roll_number': s_data.get('roll_number', 'N/A'),
                    'classroom': c_name
                }
        
        if r_id not in rooms_lookup:
            r_doc = db.collection('classrooms').document(str(r_id)).get()
            if r_doc.exists:
                r_data = r_doc.to_dict()
                rooms_lookup[r_id] = f"{r_data['name']}-{r_data['section']}"
    
    # Build attendance summary per room
    marked_ids = {a['student_id'] for a in attendance_records}
    present_ids = {a['student_id'] for a in attendance_records if a.get('status') == 'present'}
    absent_ids = {a['student_id'] for a in attendance_records if a.get('status') == 'absent'}
    
    # Group records by room
    room_records = {}
    for a_doc in arrs:
        a = a_doc.to_dict()
        r_id = a['room_id']
        s_id = a['student_id']
        room_name = rooms_lookup.get(r_id, 'Unknown')
        
        if room_name not in room_records:
            room_records[room_name] = []
        
        att_entry = next((r for r in attendance_records if r['student_id'] == s_id), None)
        
        room_records[room_name].append({
            'student': all_students.get(s_id, {'name': 'Unknown', 'roll_number': 'N/A', 'classroom': 'Unknown'}),
            'room': room_name,
            'paper_set': a.get('paper_set', 'A'),
            'status': att_entry.get('status', 'unmarked') if att_entry else 'unmarked',
            'marked_by': att_entry.get('marked_by', '') if att_entry else '',
            'marked_at': att_entry.get('marked_at', '') if att_entry else ''
        })
    
    total_students = len(all_students)
    stats = {
        'total': total_students,
        'present': len(present_ids),
        'absent': len(absent_ids),
        'unmarked': total_students - len(marked_ids),
        'percentage': round((len(present_ids) / total_students * 100), 1) if total_students else 0
    }
    
    return render_template('attendance.html', test=test, room_records=room_records, stats=stats)

@app.route('/tests/<test_id>/export/<format>/<report_type>')
def export_seating(test_id, format, report_type):
    from utils import export_to_excel, export_to_pdf
    class_filter = request.args.get('class_id')
    
    doc = db.collection('tests').document(str(test_id)).get()
    if not doc.exists:
        flash('Test not found!')
        return redirect(url_for('list_tests'))
    
    test_data = doc.to_dict() | {'id': doc.id}
    
    # If filtering by class, update title for the report header
    class_name_suffix = ""
    if class_filter:
        c_doc = db.collection('classrooms').document(str(class_filter)).get()
        if c_doc.exists:
            c_data = c_doc.to_dict()
            class_name_suffix = f" - {c_data.get('name')} {c_data.get('section')}"
            test_data['title'] += class_name_suffix
            
    test = type('obj', (object,), test_data)
    
    arrangements_docs = db.collection('seating_arrangements').where(filter=FieldFilter('test_id', '==', str(test_id))).get()
    
    # Pre-fetch rooms and students to avoid N+1
    rooms_lookup = {}
    students_lookup = {}
    
    arrangements = []
    for a_doc in arrangements_docs:
        a = a_doc.to_dict() | {'id': a_doc.id}
        s_id = a['student_id']
        r_id = a['room_id']
        
        if s_id not in students_lookup:
            s_doc = db.collection('students').document(str(s_id)).get()
            if s_doc.exists:
                s_data = s_doc.to_dict() | {'id': s_doc.id}
                c_doc = db.collection('classrooms').document(str(s_data['classroom_id'])).get()
                s_data['classroom'] = type('obj', (object,), (c_doc.to_dict() | {'id': c_doc.id}) if c_doc.exists else {})
                students_lookup[s_id] = type('obj', (object,), s_data)
        
        student_obj = students_lookup.get(s_id)
        
        # Apply class filter if requested
        if class_filter and student_obj:
            if str(getattr(student_obj, 'classroom_id', '')) != str(class_filter):
                continue
        
        if r_id not in rooms_lookup:
            r_doc = db.collection('classrooms').document(str(r_id)).get()
            if r_doc.exists:
                rooms_lookup[r_id] = type('obj', (object,), r_doc.to_dict() | {'id': r_doc.id})
        
        a['student'] = students_lookup.get(s_id)
        a['room'] = rooms_lookup.get(r_id)
        
        # Also need supervisor for teacher report
        a['supervisor'] = None
        blocks = test_data.get('exam_blocks', [])
        for b in blocks:
            if b['room_id'] == str(r_id):
                sup_id = b.get('supervisor_id')
                if sup_id:
                    sup_doc = db.collection('supervisors').document(str(sup_id)).get()
                    if sup_doc.exists:
                        a['supervisor'] = type('obj', (object,), sup_doc.to_dict() | {'id': sup_doc.id})
                break
                
        arrangements.append(type('obj', (object,), a))
    
    if format == 'excel':
        file_data = export_to_excel(test, arrangements, report_type)
        mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        extension = 'xlsx'
    else:
        file_data = export_to_pdf(test, arrangements, report_type)
        mimetype = 'application/pdf'
        extension = 'pdf'
        
    return send_file(
        file_data,
        as_attachment=True,
        download_name=f"{test.title}_{report_type}.{extension}",
        mimetype=mimetype
    )

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
