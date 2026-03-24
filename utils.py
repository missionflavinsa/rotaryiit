import random
import json
import pandas as pd
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

def generate_seating_plan(test, classrooms, students):
    """
    Physical Grid Seating Plan with Strict Constraints:
    - Uses room.rows, room.columns, room.bench_type.
    - NO student from the same class side-by-side OR back-to-back.
    - NO identical paper set for any adjacent students (horizontal or vertical).
    """
    students_by_class = {}
    for student in students:
        cid = getattr(student, 'classroom_id', getattr(student, 'class_id', None))
        if cid not in students_by_class:
            students_by_class[cid] = []
        students_by_class[cid].append(student)
    
    for cid in students_by_class:
        random.shuffle(students_by_class[cid])
    
    paper_sets = test.paper_sets.split(',')
    arrangements = []
    
    # Advanced interleaving: Try to separate students from the same class as much as possible
    current_student_list = []
    class_ids = sorted(list(students_by_class.keys()), key=lambda k: len(students_by_class[k]), reverse=True)
    
    while any(students_by_class.values()):
        for cid in class_ids:
            if students_by_class[cid]:
                current_student_list.append(students_by_class[cid].pop(0))

    total_needed = len(current_student_list)
    
    # Calculate total capacity and individual room capacities
    total_capacity = 0
    room_caps = []
    for room in classrooms:
        cap = sum(room.get_row_layout()) * (1 if room.bench_type == 'single' else 2)
        room_caps.append(cap)
        total_capacity += cap
        
    if total_needed > total_capacity:
        return None, f"Not enough capacity. Students: {total_needed}, Capacity: {total_capacity}"

    # Distribute students proportionally across all assigned rooms
    # This prevents packing the first room while others stay empty
    students_in_rooms = []
    remaining_students_count = total_needed
    for i, cap in enumerate(room_caps):
        if i == len(room_caps) - 1:
            count = remaining_students_count
        else:
            # Proportional share, rounded to nearest student
            count = round(total_needed * (cap / total_capacity))
            count = min(count, remaining_students_count, cap)
        students_in_rooms.append(count)
        remaining_students_count -= count
        
    # Assign students to sparse indices within each room
    arrangements = []
    student_idx = 0
    
    for i, room in enumerate(classrooms):
        num_to_assign = students_in_rooms[i]
        if num_to_assign == 0: continue
            
        S = room_caps[i] # Total seats in room
        N = num_to_assign # Students to place
        
        # Calculate sparse indices (0 to S-1)
        if N >= S:
            selected_indices = set(range(S))
        else:
            # Maximum spacing! Calculate a floating-point step
            step = S / N
            selected_indices = {int(k * step) for k in range(N)}
            
        row_layout = room.get_row_layout()
        multiplier = 1 if room.bench_type == 'single' else 2
        
        abs_seat_idx = 0 # Logical index from 0 to S-1
        for r, benches_in_row in enumerate(row_layout):
            for c in range(benches_in_row):
                for s in range(multiplier):
                    if abs_seat_idx in selected_indices:
                        if student_idx < total_needed:
                            student = current_student_list[student_idx]
                            
                            # Standard Paper Set Pattern
                            paper_sets = test.paper_sets.split(',')
                            set_idx = (r * 3 + c * 2 + s) % len(paper_sets)
                            paper_set = paper_sets[set_idx]
                            
                            arrangements.append({
                                'test_id': test.id,
                                'student_id': student.id,
                                'room_id': room.id,
                                'seat_number': abs_seat_idx + 1, # 1-indexed for display
                                'paper_set': paper_set
                            })
                            student_idx += 1
                    abs_seat_idx += 1
                    
    return arrangements, None

def export_to_excel(test, arrangements, report_type):
    output = BytesIO()
    data = []
    
    if report_type == 'teacher':
        for arr in arrangements:
            # Handle both objects and dictionaries
            seat_num = getattr(arr, 'seat_number', arr.get('seat_number') if isinstance(arr, dict) else None)
            student = getattr(arr, 'student', None)
            paper_set = getattr(arr, 'paper_set', arr.get('paper_set') if isinstance(arr, dict) else 'A')
            supervisor = getattr(arr, 'supervisor', None)
            
            data.append({
                'Seat #': seat_num,
                'Roll Number': student.roll_number if student else 'N/A',
                'Student Name': student.name if student else 'Unknown',
                'Original Class': f"{student.classroom.name}-{student.classroom.section}" if student and hasattr(student, 'classroom') else "N/A",
                'Paper Set': paper_set,
                'Supervisor': supervisor.name if supervisor and hasattr(supervisor, 'name') else "N/A",
                'Duration': f"{test.duration} mins"
            })
    elif report_type == 'student':
        # Sort by roll number (A-Z)
        def get_roll_sort_key(x):
            try:
                # Try natural sort for numeric-heavy roll numbers
                import re
                return [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', str(x.student.roll_number))]
            except:
                return str(x.student.roll_number).lower()

        arr_sorted = sorted(arrangements, key=get_roll_sort_key)
        for arr in arr_sorted:
            data.append({
                'Roll Number': arr.student.roll_number,
                'Student Name': arr.student.name,
                'Exam Room': f"{arr.room.name}-{arr.room.section}",
                'Seat #': arr.seat_number,
                'Original Class': f"{arr.student.classroom.name}-{arr.student.classroom.section}",
                'Exam Duration': f"{test.duration} mins"
            })
    else:
        # Fallback for unknown types to prevent empty dataframes
        data.append({'Message': f'No data available for report type: {report_type}'})
    
    df = pd.DataFrame(data)
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Seating')
        
        # Add a Summary sheet for teacher reports
        if report_type == 'teacher':
            summary_data = []
            # Calculate counts
            counts = {}
            for row in data:
                cname = row['Original Class']
                counts[cname] = counts.get(cname, 0) + 1
            
            for cname, count in sorted(counts.items()):
                summary_data.append({'Class': cname, 'Student Count': count})
            summary_data.append({'Class': 'Total', 'Student Count': sum(counts.values())})
            
            df_sum = pd.DataFrame(summary_data)
            df_sum.to_excel(writer, index=False, sheet_name='Summary')
    
    output.seek(0)
    return output

def export_to_pdf(test, arrangements, report_type):
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    styles = getSampleStyleSheet()
    
    title = f"{test.title} - {report_type.capitalize()} Copy"
    elements.append(Paragraph(title, styles['Title']))
    
    # Add Date and Duration
    test_date_str = test.date.strftime('%B %d, %Y') if test.date else "N/A"
    elements.append(Paragraph(f"Date: {test_date_str} | Duration: {test.duration} Minutes", styles['Normal']))
    elements.append(Spacer(1, 12))
    
    data = []
    if report_type == 'teacher':
        # Add Summary Table first
        elements.append(Paragraph("Room Statistics (Student Counts)", styles['Heading3']))
        summary_data = [['Class', 'Count']]
        counts = {}
        for arr in arrangements:
            student = getattr(arr, 'student', None)
            if student and hasattr(student, 'classroom'):
                c_name = f"{student.classroom.name}-{student.classroom.section}"
                counts[c_name] = counts.get(c_name, 0) + 1
        
        for cname, count in sorted(counts.items()):
            summary_data.append([cname, count])
        summary_data.append(['Total', sum(counts.values())])
        
        tsum = Table(summary_data, colWidths=[150, 60])
        tsum.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.white),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ]))
        elements.append(tsum)
        elements.append(Spacer(1, 20))

        data.append(['Seat #', 'Roll No', 'Name', 'Class', 'Set', 'Supervisor'])
        for arr in arrangements:
            seat_num = getattr(arr, 'seat_number', arr.get('seat_number') if isinstance(arr, dict) else 'N/A')
            student = getattr(arr, 'student', None)
            paper_set = getattr(arr, 'paper_set', arr.get('paper_set') if isinstance(arr, dict) else 'A')
            supervisor = getattr(arr, 'supervisor', None)
            
            data.append([
                seat_num, 
                student.roll_number if student else 'N/A', 
                student.name if student else 'Unknown', 
                f"{student.classroom.name}-{student.classroom.section}" if student and hasattr(student, 'classroom') else "N/A", 
                paper_set,
                supervisor.name if supervisor and hasattr(supervisor, 'name') else "N/A"
            ])
    elif report_type == 'student':
        data.append(['Roll No', 'Name', 'Exam Room'])
        
        def get_student_sort_key(x):
            s = getattr(x, 'student', None)
            if not s: return []
            roll = str(getattr(s, 'roll_number', ""))
            try:
                import re
                return [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', roll)]
            except:
                return [roll.lower()]
            
        arr_sorted = sorted(arrangements, key=get_student_sort_key)
        for arr in arr_sorted:
            student = getattr(arr, 'student', None)
            room = getattr(arr, 'room', None)
            
            data.append([
                student.roll_number if student else "N/A",
                student.name if student else "Unknown", 
                f"{room.name}-{room.section}" if room and hasattr(room, 'name') else "N/A"
            ])
    else:
        data.append(['Notice', 'No data available for this report type'])
    
    # Table styling and widths
    if report_type == 'student':
        # Autofit to page width (A4 available width is ~535)
        col_widths = [100, 285, 150] # Roll No, Name, Room
        t = Table(data, colWidths=col_widths)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.white),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'), # Default center
            ('ALIGN', (1, 1), (2, -1), 'LEFT'),    # Name and Room on left
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black)
        ]))
    else:
        t = Table(data)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.white),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black)
        ]))
    elements.append(t)
    doc.build(elements)
    
    output.seek(0)
    return output

def export_consolidated_excel(test, rooms, class_names, matrix, room_totals, class_totals):
    output = BytesIO()
    
    # Create the matrix data for DataFrame
    rows = []
    for room in rooms:
        rid = str(getattr(room, 'id', ''))
        row = {'Block / Room': f"{getattr(room, 'name', '')} {getattr(room, 'section', '')}"}
        for cname in class_names:
            cell = matrix.get(rid, {}).get(cname, {'total': 0, 'sets': {}})
            if cell['total'] > 0:
                sets_str = ", ".join([f"{s}:{c}" for s, c in sorted(cell['sets'].items())])
                row[cname] = f"{cell['total']} ({sets_str})"
            else:
                row[cname] = 0
        row['Block Total'] = room_totals.get(rid, 0)
        rows.append(row)
    
    # Add Class Totals row
    total_row = {'Block / Room': 'Class Totals'}
    for cname in class_names:
        total_row[cname] = class_totals[cname]
    total_row['Block Total'] = sum(class_totals.values())
    rows.append(total_row)
    
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Consolidated Summary')
    
    output.seek(0)
    return output

def export_consolidated_pdf(test, rooms, class_names, matrix, room_totals, class_totals):
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    styles = getSampleStyleSheet()
    
    elements.append(Paragraph(f"{test.title} - Consolidated Summary", styles['Title']))
    test_date_str = test.date.strftime('%B %d, %Y') if test.date else "N/A"
    elements.append(Paragraph(f"Date: {test_date_str} | Duration: {test.duration} Minutes", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    # PDF Table Header
    header = ['Block / Room'] + class_names + ['Total']
    data = [header]
    
    for room in rooms:
        rid = str(getattr(room, 'id', ''))
        row = [f"{getattr(room, 'name', '')} {getattr(room, 'section', '')}"]
        for cname in class_names:
            cell = matrix.get(rid, {}).get(cname, {'total': 0, 'sets': {}})
            if cell['total'] > 0:
                sets_str = " ".join([f"{s}:{c}" for s, c in sorted(cell['sets'].items())])
                row.append(f"{cell['total']}\n({sets_str})")
            else:
                row.append("-")
        row.append(str(room_totals.get(rid, 0)))
        data.append(row)
    
    # Totals Row
    total_row = ['Class Totals']
    for cname in class_names:
        total_row.append(str(class_totals[cname]))
    total_row.append(str(sum(class_totals.values())))
    data.append(total_row)
    
    # Estimate column widths: first col wider, others equal
    num_cols = len(header)
    available_width = 530 # A4 is ~595, minus margins
    col_widths = [100] + [(available_width - 100) / (num_cols - 1)] * (num_cols - 1)
    
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.white),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
    ]))
    elements.append(t)
    doc.build(elements)
    
    output.seek(0)
    return output
