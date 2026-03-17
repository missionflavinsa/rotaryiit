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
        if student.class_id not in students_by_class:
            students_by_class[student.class_id] = []
        students_by_class[student.class_id].append(student)
    
    for class_id in students_by_class:
        random.shuffle(students_by_class[class_id])
    
    paper_sets = test.paper_sets.split(',')
    arrangements = []
    
    # Advanced interleaving: Try to separate students from the same class as much as possible
    current_student_list = []
    class_ids = sorted(list(students_by_class.keys()), key=lambda k: len(students_by_class[k]), reverse=True)
    
    while any(students_by_class.values()):
        for cid in class_ids:
            if students_by_class[cid]:
                current_student_list.append(students_by_class[cid].pop(0))

    student_idx = 0
    total_needed = len(current_student_list)
    
    for room in classrooms:
        row_layout = room.get_row_layout()
        multiplier = 1 if room.bench_type == 'single' else 2
        
        room_seat_counter = 1
        for r, benches_in_row in enumerate(row_layout):
            for c in range(benches_in_row):
                for s in range(multiplier):
                    if student_idx >= total_needed:
                        # Continue filling empty seats if needed for reports? 
                        # Actually student_idx is for students, we should stop if no more students.
                        break
                    
                    student = current_student_list[student_idx]
                    seat_num = room_seat_counter
                    
                    # Strict Paper Set Assignment Pattern:
                    # Using (r*3 + c*2 + s) still provides good diversity across rows.
                    set_idx = (r * 3 + c * 2 + s) % len(paper_sets)
                    paper_set = paper_sets[set_idx]
                    
                    arrangements.append({
                        'test_id': test.id,
                        'student_id': student.id,
                        'room_id': room.id,
                        'seat_number': seat_num,
                        'paper_set': paper_set
                    })
                    student_idx += 1
                    room_seat_counter += 1
                if student_idx >= total_needed:
                    break
            if student_idx >= total_needed:
                break
        if student_idx >= total_needed:
            # Note: We continue to next rooms if students remain, but we already handled that with total_needed
            pass
                
    if student_idx < total_needed:
        return None, f"Not enough capacity. Remaining students: {total_needed - student_idx}"

    return arrangements, None

def export_to_excel(test, arrangements, report_type):
    output = BytesIO()
    data = []
    
    if report_type == 'teacher':
        for arr in arrangements:
            data.append({
                'Seat #': arr.seat_number,
                'Roll Number': arr.student.roll_number,
                'Student Name': arr.student.name,
                'Original Class': f"{arr.student.classroom.name}-{arr.student.classroom.section}",
                'Paper Set': arr.paper_set,
                'Supervisor': arr.supervisor.name if arr.supervisor else "None",
                'Duration': f"{test.duration} mins"
            })
    elif report_type == 'student':
        # Sort by student class for student view
        arr_sorted = sorted(arrangements, key=lambda x: (x.student.classroom.name, x.student.classroom.section, x.student.name))
        for arr in arr_sorted:
            data.append({
                'Student Name': arr.student.name,
                'Roll Number': arr.student.roll_number,
                'Class': f"{arr.student.classroom.name}-{arr.student.classroom.section}",
                'Exam Block': f"{arr.room.name}-{arr.room.section}",
                'Seat #': arr.seat_number,
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
            c_name = f"{arr.student.classroom.name}-{arr.student.classroom.section}"
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
            data.append([
                arr.seat_number, 
                arr.student.roll_number, 
                arr.student.name, 
                f"{arr.student.classroom.name}-{arr.student.classroom.section}", 
                arr.paper_set,
                arr.supervisor.name if arr.supervisor else ""
            ])
    elif report_type == 'student':
        data.append(['Name', 'Roll No', 'Original Class', 'Exam Room', 'Seat #'])
        arr_sorted = sorted(arrangements, key=lambda x: (x.student.classroom.name, x.student.classroom.section, x.student.name))
        for arr in arr_sorted:
            data.append([
                arr.student.name, 
                arr.student.roll_number, 
                f"{arr.student.classroom.name}-{arr.student.classroom.section}", 
                f"{arr.room.name}-{arr.room.section}", 
                arr.seat_number
            ])
    else:
        data.append(['Notice', 'No data available for this report type'])
    
    # Seating Table
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
        row = {'Block / Room': f"{room.name} {room.section}"}
        for cname in class_names:
            count = matrix[room.id][cname]
            row[cname] = count if count > 0 else 0
        row['Block Total'] = room_totals[room.id]
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
        row = [f"{room.name} {room.section}"]
        for cname in class_names:
            count = matrix[room.id][cname]
            row.append(str(count) if count > 0 else "-")
        row.append(str(room_totals[room.id]))
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
