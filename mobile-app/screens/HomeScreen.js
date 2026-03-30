import React, { useState, useEffect } from 'react';
import {
  View, Text, FlatList, TouchableOpacity,
  StyleSheet, ActivityIndicator, RefreshControl
} from 'react-native';
import { collection, getDocs } from 'firebase/firestore';
import { signOut } from 'firebase/auth';
import { db, auth } from '../firebaseConfig';
import { Ionicons } from '@expo/vector-icons';

export default function HomeScreen({ route, navigation }) {
  const { supervisor } = route.params;
  const [tests, setTests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchTests = async () => {
    try {
      const testsSnap = await getDocs(collection(db, 'tests'));
      const assignedTests = [];

      for (const d of testsSnap.docs) {
        const test = { id: d.id, ...d.data() };
        const blocks = test.exam_blocks || [];

        // Find blocks assigned to this supervisor
        const myBlocks = blocks.filter(b => b.supervisor_id === supervisor.id);
        if (myBlocks.length > 0) {
          // Fetch room names for my blocks
          const myRoomInfos = [];
          for (const block of myBlocks) {
            const { getDoc, doc } = await import('firebase/firestore');
            const rDoc = await getDoc(doc(db, 'classrooms', block.room_id));
            if (rDoc.exists()) {
              const r = rDoc.data();
              myRoomInfos.push(`${r.name}-${r.section}`);
            } else {
              myRoomInfos.push('Unknown Room');
            }
          }

          assignedTests.push({
            ...test,
            myRoomIds: myBlocks.map(b => b.room_id),
            myRoomNames: myRoomInfos.join(', '),
          });
        }
      }

      // Sort by date (newest first)
      assignedTests.sort((a, b) => {
        const dateA = a.date?.toDate ? a.date.toDate() : (a.date ? new Date(a.date) : new Date(0));
        const dateB = b.date?.toDate ? b.date.toDate() : (b.date ? new Date(b.date) : new Date(0));
        return dateB - dateA;
      });

      setTests(assignedTests);
    } catch (error) {
      console.error('Error fetching tests:', error);
    }
    setLoading(false);
    setRefreshing(false);
  };

  useEffect(() => {
    fetchTests();
  }, []);

  const handleLogout = async () => {
    await signOut(auth);
    navigation.replace('Login');
  };

  const renderTest = ({ item }) => {
    // Handle Firestore Timestamp vs regular Date string
    const dateObj = item.date?.toDate ? item.date.toDate() : (item.date ? new Date(item.date) : null);
    const dateStr = dateObj && !isNaN(dateObj)
      ? dateObj.toLocaleDateString('en-IN', {
          day: 'numeric', month: 'short', year: 'numeric'
        })
      : 'No date';

    return (
      <TouchableOpacity
        style={styles.card}
        onPress={() => navigation.navigate('Attendance', {
          test: item,
          supervisor,
          roomIds: item.myRoomIds,
        })}
      >
        <View style={styles.cardHeader}>
          <Text style={styles.cardTitle}>{item.title}</Text>
          <Ionicons name="chevron-forward" size={20} color="#a78bfa" />
        </View>
        <View style={styles.cardMeta}>
          <View style={styles.metaItem}>
            <Ionicons name="calendar-outline" size={14} color="#888" />
            <Text style={styles.metaText}>{dateStr}</Text>
          </View>
          <View style={styles.metaItem}>
            <Ionicons name="time-outline" size={14} color="#888" />
            <Text style={styles.metaText}>{item.duration || '—'} mins</Text>
          </View>
          <View style={styles.metaItem}>
            <Ionicons name="business-outline" size={14} color="#888" />
            <Text style={styles.metaText}>{item.myRoomNames || 'No Rooms'}</Text>
          </View>
        </View>
        <View style={styles.badge}>
          <Text style={styles.badgeText}>Sets: {item.paper_sets || 'A,B,C,D'}</Text>
        </View>
      </TouchableOpacity>
    );
  };

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#7c3aed" />
        <Text style={styles.loadingText}>Loading your tests...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Header Info */}
      <View style={styles.welcomeBar}>
        <View>
          <Text style={styles.welcomeText}>Welcome,</Text>
          <Text style={styles.supervisorName}>{supervisor.name}</Text>
        </View>
        <TouchableOpacity onPress={handleLogout} style={styles.logoutBtn}>
          <Ionicons name="log-out-outline" size={22} color="#f87171" />
        </TouchableOpacity>
      </View>

      {tests.length === 0 ? (
        <View style={styles.center}>
          <Ionicons name="clipboard-outline" size={64} color="#333" />
          <Text style={styles.emptyText}>No tests assigned to you yet.</Text>
        </View>
      ) : (
        <FlatList
          data={tests}
          renderItem={renderTest}
          keyExtractor={(item) => item.id}
          contentContainerStyle={{ paddingBottom: 24 }}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => { setRefreshing(true); fetchTests(); }}
              tintColor="#7c3aed"
            />
          }
        />
      )}
    </View>
  );
}

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
  welcomeBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 20,
    paddingBottom: 16,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.08)',
  },
  welcomeText: {
    color: '#888',
    fontSize: 14,
  },
  supervisorName: {
    color: '#fff',
    fontSize: 20,
    fontWeight: 'bold',
  },
  logoutBtn: {
    padding: 8,
    backgroundColor: 'rgba(248,113,113,0.1)',
    borderRadius: 10,
  },
  card: {
    backgroundColor: 'rgba(255,255,255,0.06)',
    borderRadius: 16,
    padding: 18,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  cardTitle: {
    color: '#fff',
    fontSize: 17,
    fontWeight: '700',
    flex: 1,
  },
  cardMeta: {
    flexDirection: 'row',
    marginTop: 12,
    gap: 16,
  },
  metaItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  metaText: {
    color: '#888',
    fontSize: 13,
  },
  badge: {
    alignSelf: 'flex-start',
    backgroundColor: 'rgba(124,58,237,0.2)',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 8,
    marginTop: 10,
  },
  badgeText: {
    color: '#a78bfa',
    fontSize: 12,
    fontWeight: '600',
  },
  emptyText: {
    color: '#555',
    fontSize: 16,
    marginTop: 16,
  },
});
