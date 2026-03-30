import React, { useState, useEffect } from 'react';
import {
  View, Text, FlatList, TouchableOpacity,
  StyleSheet, ActivityIndicator, Alert, RefreshControl
} from 'react-native';
import {
  collection, query, where, getDocs, doc, setDoc, serverTimestamp
} from 'firebase/firestore';
import { db } from '../firebaseConfig';
import { Ionicons } from '@expo/vector-icons';

export default function AttendanceScreen({ route }) {
  const { test, supervisor, roomIds } = route.params;
  const [students, setStudents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [submitting, setSubmitting] = useState({});
  const [roomNames, setRoomNames] = useState({});

  // Stats
  const presentCount = students.filter(s => s.status === 'present').length;
  const absentCount = students.filter(s => s.status === 'absent').length;
  const unmarkedCount = students.filter(s => s.status === 'unmarked').length;

  const fetchStudents = async () => {
    try {
      // Fetch seating arrangements for this test
      const arrQuery = query(
        collection(db, 'seating_arrangements'),
        where('test_id', '==', test.id)
      );
      const arrSnap = await getDocs(arrQuery);

      // Filter to only this supervisor's rooms
      const myArrangements = [];
      arrSnap.forEach((d) => {
        const arr = { id: d.id, ...d.data() };
        if (roomIds.includes(arr.room_id)) {
          myArrangements.push(arr);
        }
      });

      // Fetch room names
      const rNames = {};
      for (const rid of roomIds) {
        if (!rNames[rid]) {
          const rSnap = await getDocs(query(collection(db, 'classrooms'), where('__name__', '==', rid)));
          // Fallback: get by document ID
          const { getDoc } = await import('firebase/firestore');
          const rDoc = await getDoc(doc(db, 'classrooms', rid));
          if (rDoc.exists()) {
            const r = rDoc.data();
            rNames[rid] = `${r.name}-${r.section}`;
          }
        }
      }
      setRoomNames(rNames);

      // Fetch student details
      const studentList = [];
      for (const arr of myArrangements) {
        const { getDoc } = await import('firebase/firestore');
        const sDoc = await getDoc(doc(db, 'students', arr.student_id));
        if (sDoc.exists()) {
          const sData = sDoc.data();

          // Get classroom name
          let className = 'Unknown';
          if (sData.classroom_id) {
            const cDoc = await getDoc(doc(db, 'classrooms', sData.classroom_id));
            if (cDoc.exists()) {
              const c = cDoc.data();
              className = `${c.name}-${c.section}`;
            }
          }

          studentList.push({
            id: arr.student_id,
            arrId: arr.id,
            name: sData.name || 'Unknown',
            roll_number: sData.roll_number || 'N/A',
            classroom: className,
            paper_set: arr.paper_set || 'A',
            room_id: arr.room_id,
            room_name: rNames[arr.room_id] || 'Unknown',
            seat_number: arr.seat_number,
            status: 'unmarked', // Will be updated from attendance collection
          });
        }
      }

      // Fetch existing attendance records
      const attQuery = query(
        collection(db, 'attendance'),
        where('test_id', '==', test.id)
      );
      const attSnap = await getDocs(attQuery);
      const attMap = {};
      attSnap.forEach((d) => {
        const att = d.data();
        attMap[att.student_id] = att.status;
      });

      // Merge attendance status
      studentList.forEach((s) => {
        if (attMap[s.id]) {
          s.status = attMap[s.id];
        }
      });

      // Sort by roll number
      studentList.sort((a, b) => a.roll_number.localeCompare(b.roll_number));

      setStudents(studentList);
    } catch (error) {
      console.error('Error fetching students:', error);
      Alert.alert('Error', 'Failed to load student list.');
    }
    setLoading(false);
    setRefreshing(false);
  };

  useEffect(() => {
    fetchStudents();
  }, []);

  const markAttendance = async (student, status) => {
    setSubmitting(prev => ({ ...prev, [student.id]: true }));
    try {
      const attDocId = `${test.id}_${student.id}`;
      await setDoc(doc(db, 'attendance', attDocId), {
        test_id: test.id,
        student_id: student.id,
        room_id: student.room_id,
        supervisor_id: supervisor.id,
        roll_number: student.roll_number,
        student_name: student.name,
        paper_set: student.paper_set,
        status: status,
        marked_at: new Date().toISOString(),
        marked_by: supervisor.name || supervisor.email,
      });

      // Update local state
      setStudents(prev =>
        prev.map(s => s.id === student.id ? { ...s, status } : s)
      );
    } catch (error) {
      console.error('Error marking attendance:', error);
      Alert.alert('Error', 'Could not save attendance. Check your connection.');
    }
    setSubmitting(prev => ({ ...prev, [student.id]: false }));
  };

  const markAllPresent = () => {
    Alert.alert(
      'Mark All Present',
      'Are you sure you want to mark all students as present?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Yes',
          onPress: async () => {
            for (const student of students) {
              if (student.status !== 'present') {
                await markAttendance(student, 'present');
              }
            }
          }
        }
      ]
    );
  };

  const renderStudent = ({ item, index }) => (
    <View style={styles.studentCard}>
      <View style={styles.studentInfo}>
        <View style={styles.studentHeader}>
          <Text style={styles.rollNumber}>{item.roll_number}</Text>
          <View style={[styles.setBadge, { backgroundColor: getSetColor(item.paper_set) }]}>
            <Text style={styles.setBadgeText}>Set {item.paper_set}</Text>
          </View>
        </View>
        <Text style={styles.studentName}>{item.name}</Text>
        <Text style={styles.studentClass}>{item.classroom} → {item.room_name}</Text>
      </View>

      <View style={styles.attendanceButtons}>
        {submitting[item.id] ? (
          <ActivityIndicator size="small" color="#7c3aed" />
        ) : (
          <>
            <TouchableOpacity
              style={[
                styles.attBtn,
                styles.presentBtn,
                item.status === 'present' && styles.presentBtnActive,
              ]}
              onPress={() => markAttendance(item, 'present')}
            >
              <Ionicons
                name={item.status === 'present' ? 'checkmark-circle' : 'checkmark-circle-outline'}
                size={20}
                color={item.status === 'present' ? '#fff' : '#4ade80'}
              />
              <Text style={[
                styles.attBtnText,
                item.status === 'present' && { color: '#fff' }
              ]}>P</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[
                styles.attBtn,
                styles.absentBtn,
                item.status === 'absent' && styles.absentBtnActive,
              ]}
              onPress={() => markAttendance(item, 'absent')}
            >
              <Ionicons
                name={item.status === 'absent' ? 'close-circle' : 'close-circle-outline'}
                size={20}
                color={item.status === 'absent' ? '#fff' : '#f87171'}
              />
              <Text style={[
                styles.attBtnText,
                styles.absentText,
                item.status === 'absent' && { color: '#fff' }
              ]}>A</Text>
            </TouchableOpacity>
          </>
        )}
      </View>
    </View>
  );

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#7c3aed" />
        <Text style={styles.loadingText}>Loading students...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Stats Bar */}
      <View style={styles.statsBar}>
        <View style={styles.statItem}>
          <Text style={styles.statNumber}>{students.length}</Text>
          <Text style={styles.statLabel}>Total</Text>
        </View>
        <View style={styles.statItem}>
          <Text style={[styles.statNumber, { color: '#4ade80' }]}>{presentCount}</Text>
          <Text style={styles.statLabel}>Present</Text>
        </View>
        <View style={styles.statItem}>
          <Text style={[styles.statNumber, { color: '#f87171' }]}>{absentCount}</Text>
          <Text style={styles.statLabel}>Absent</Text>
        </View>
        <View style={styles.statItem}>
          <Text style={[styles.statNumber, { color: '#fbbf24' }]}>{unmarkedCount}</Text>
          <Text style={styles.statLabel}>Pending</Text>
        </View>
      </View>

      {/* Quick Actions */}
      <TouchableOpacity style={styles.markAllBtn} onPress={markAllPresent}>
        <Ionicons name="checkmark-done" size={18} color="#4ade80" />
        <Text style={styles.markAllText}>Mark All Present</Text>
      </TouchableOpacity>

      {/* Student List */}
      <FlatList
        data={students}
        renderItem={renderStudent}
        keyExtractor={(item) => item.id}
        contentContainerStyle={{ paddingBottom: 24 }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => { setRefreshing(true); fetchStudents(); }}
            tintColor="#7c3aed"
          />
        }
      />
    </View>
  );
}

const getSetColor = (set) => {
  const colors = {
    'A': 'rgba(124,58,237,0.3)',
    'B': 'rgba(59,130,246,0.3)',
    'C': 'rgba(234,179,8,0.3)',
    'D': 'rgba(236,72,153,0.3)',
  };
  return colors[set] || 'rgba(124,58,237,0.3)';
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0a0620',
    padding: 16,
  },
  center: {
    flex: 1,
    backgroundColor: '#0a0620',
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    color: '#888',
    marginTop: 12,
  },
  statsBar: {
    flexDirection: 'row',
    backgroundColor: 'rgba(255,255,255,0.06)',
    borderRadius: 14,
    padding: 14,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
    justifyContent: 'space-around',
  },
  statItem: {
    alignItems: 'center',
  },
  statNumber: {
    color: '#fff',
    fontSize: 22,
    fontWeight: 'bold',
  },
  statLabel: {
    color: '#888',
    fontSize: 11,
    marginTop: 2,
  },
  markAllBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: 'rgba(74,222,128,0.1)',
    borderRadius: 10,
    padding: 10,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: 'rgba(74,222,128,0.2)',
  },
  markAllText: {
    color: '#4ade80',
    fontWeight: '600',
    fontSize: 14,
  },
  studentCard: {
    flexDirection: 'row',
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderRadius: 14,
    padding: 14,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.06)',
    alignItems: 'center',
  },
  studentInfo: {
    flex: 1,
  },
  studentHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 4,
  },
  rollNumber: {
    color: '#a78bfa',
    fontSize: 14,
    fontWeight: '700',
  },
  setBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 6,
  },
  setBadgeText: {
    color: '#fff',
    fontSize: 11,
    fontWeight: '600',
  },
  studentName: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '500',
    marginBottom: 2,
  },
  studentClass: {
    color: '#666',
    fontSize: 12,
  },
  attendanceButtons: {
    flexDirection: 'row',
    gap: 8,
    marginLeft: 8,
  },
  attBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 10,
    borderWidth: 1,
  },
  presentBtn: {
    borderColor: 'rgba(74,222,128,0.3)',
    backgroundColor: 'rgba(74,222,128,0.08)',
  },
  presentBtnActive: {
    backgroundColor: '#16a34a',
    borderColor: '#16a34a',
  },
  absentBtn: {
    borderColor: 'rgba(248,113,113,0.3)',
    backgroundColor: 'rgba(248,113,113,0.08)',
  },
  absentBtnActive: {
    backgroundColor: '#dc2626',
    borderColor: '#dc2626',
  },
  attBtnText: {
    color: '#4ade80',
    fontWeight: '700',
    fontSize: 14,
  },
  absentText: {
    color: '#f87171',
  },
});
